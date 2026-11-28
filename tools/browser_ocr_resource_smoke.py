"""Real local OCR success/cancellation cycles and Chromium resource observations.

Uses synthetic images only. Run with the same browser as browser_smoke.py.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
import time

from playwright.sync_api import sync_playwright

from browser_smoke import local_server


def process_memory(pids):
    """Sample Windows browser processes reported by CDP; units are bytes."""
    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [
            (name, ctypes.c_size_t) for name in (
                "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage",
                "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage", "QuotaNonPagedPoolUsage",
                "PagefileUsage", "PeakPagefileUsage", "PrivateUsage")]
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    working = private = counted = 0
    for pid in pids:
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            continue
        try:
            counters = Counters()
            counters.cb = ctypes.sizeof(counters)
            if psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
                working += counters.WorkingSetSize
                private += counters.PrivateUsage
                counted += 1
        finally:
            kernel.CloseHandle(handle)
    assert counted, "No browser process memory samples"
    return {"working_set_mib": round(working / 1048576, 2),
            "private_mib": round(private / 1048576, 2), "processes": counted,
            "reported_processes": len(pids)}


def run(cycles):
    with local_server() as origin, sync_playwright() as playwright:
        executable = os.environ.get('PLAYWRIGHT_CHROMIUM_EXECUTABLE')
        options = {'executable_path': executable} if executable else {'channel': 'chrome'}
        browser = playwright.chromium.launch(**options, headless=True, timeout=20000)
        try:
            context = browser.new_context()
            page = context.new_page()
            external = []
            page.on('request', lambda request: external.append(request.url)
                    if not request.url.startswith((origin + '/', 'blob:', 'data:')) else None)
            page.goto(origin, wait_until='domcontentloaded')
            cdp = context.new_cdp_session(page)
            cdp.send('Performance.enable')
            targets = browser.new_browser_cdp_session()
            created_workers = set()
            destroyed_targets = set()
            targets.on('Target.targetCreated', lambda event: created_workers.add(event['targetInfo']['targetId'])
                       if event['targetInfo']['type'] == 'worker' else None)
            targets.on('Target.targetDestroyed', lambda event: destroyed_targets.add(event['targetId']))
            targets.send('Target.setDiscoverTargets', {'discover': True})
            def memory_sample():
                pids = [p['id'] for p in targets.send('SystemInfo.getProcessInfo')['processInfo']]
                return process_memory(pids) if os.name == 'nt' else None
            def worker_count():
                return sum(t['type'] == 'worker' for t in targets.send('Target.getTargets')['targetInfos'])
            page.evaluate("""async () => {
                const {recognizeImage} = await import('/src/ocr.js');
                const canvas = document.createElement('canvas');
                canvas.width = 1000; canvas.height = 300;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = 'white'; ctx.fillRect(0, 0, 1000, 300);
                ctx.fillStyle = 'black'; ctx.font = 'bold 100px sans-serif';
                ctx.fillText('學習中文', 40, 150);
                window.fixture = await new Promise(resolve => canvas.toBlob(resolve));
                const original = Tesseract.createWorker;
                window.ocrStarted = 0;
                Tesseract.createWorker = async (...args) => {
                    const worker = await original(...args);
                    const recognize = worker.recognize.bind(worker);
                    worker.recognize = (...params) => {
                        window.ocrStarted++;
                        return recognize(...params);
                    };
                    return worker;
                };
                window.startOCR = () => {
                    window.controller = new AbortController();
                    window.outcome = null;
                    recognizeImage(window.fixture, window.controller.signal).then(
                        result => { window.outcome = {ok: !!result.trim()}; },
                        error => { window.outcome = {error: error.name}; }
                    );
                };
            }""")
            baseline = worker_count()
            samples = []
            memory_samples = []
            started = time.monotonic()
            for index in range(cycles):
                for cancel in (False, True):
                    prior_workers = set(created_workers)
                    expected = page.evaluate('window.ocrStarted') + 1
                    page.evaluate('window.startOCR()')
                    page.wait_for_function('count => window.ocrStarted >= count', arg=expected, timeout=45000)
                    if cancel:
                        page.evaluate('window.controller.abort()')
                    page.wait_for_function('window.outcome !== null', timeout=45000)
                    outcome = page.evaluate('window.outcome')
                    assert outcome == ({'error': 'AbortError'} if cancel else {'ok': True}), outcome
                    deadline = time.monotonic() + 10
                    while worker_count() > baseline and time.monotonic() < deadline:
                        page.wait_for_timeout(100)
                    assert worker_count() == baseline, 'Worker target remains after OCR'
                    new_workers = created_workers - prior_workers
                    assert new_workers, 'No real worker target creation observed'
                    assert new_workers <= destroyed_targets, 'Worker destruction event missing'
                cdp.send('HeapProfiler.collectGarbage')
                metrics = {m['name']: m['value'] for m in cdp.send('Performance.getMetrics')['metrics']}
                samples.append(round(metrics['JSHeapUsedSize'] / 1048576, 2))
                memory_samples.append(memory_sample())
                print(json.dumps({'cycle': index + 1, 'worker_targets': worker_count(),
                                  'page_js_heap_mib': samples[-1], 'browser_memory': memory_samples[-1]}), flush=True)
            assert not external, external[:5]
            print(json.dumps({'result': 'PASS', 'cycles': cycles, 'browser': browser.version,
                              'elapsed_seconds': round(time.monotonic() - started, 2),
                              'page_js_heap_mib': samples, 'created_workers': len(created_workers),
                              'destroyed_workers': len(created_workers & destroyed_targets),
                              'browser_memory': memory_samples}), flush=True)
            context.close()
        finally:
            browser.close()
        print('Browser closed', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cycles', type=int, default=20, choices=range(1, 1001), metavar='1-1000')
    run(parser.parse_args().cycles)
