"""Repeated 20-page synthetic scanned PDF import with sampled browser memory."""
import argparse
import io
import json
import os
import re
import time

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright
from browser_smoke import local_server, create_learner, create_subject
from browser_ocr_resource_smoke import process_memory


def fixture():
    pages = []
    font = ImageFont.truetype('C:/Windows/Fonts/msjh.ttc', 160)
    try:
        for number in range(1, 21):
            page = Image.new('RGB', (2480, 3508), 'white')
            ImageDraw.Draw(page).text((100, 120), f'學習中文 第{number}頁', font=font, fill='black')
            pages.append(page)
        output = io.BytesIO()
        pages[0].save(output, format='PDF', save_all=True, append_images=pages[1:], resolution=150, quality=55)
        return output.getvalue()
    finally:
        for page in pages:
            page.close()


def run(rounds):
    payload = fixture()
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
            create_learner(page, 'Synthetic OCR learner')
            create_subject(page, 'Synthetic PDF subject', 'Initial material', 'Synthetic question')
            targets = browser.new_browser_cdp_session()
            cdp = context.new_cdp_session(page)
            def sample():
                return process_memory(targets.send('SystemInfo.getProcessInfo')['processInfo'])
            for index in range(rounds):
                name = f'large-scan-{index + 1}.pdf'
                started = time.monotonic()
                page.locator('#materialFile').set_input_files({'name': name, 'mimeType': 'application/pdf', 'buffer': payload})
                deadline = started + 120
                peak_private = peak_working = samples = 0
                while True:
                    memory = sample()
                    peak_private = max(peak_private, memory['private_mib'])
                    peak_working = max(peak_working, memory['working_set_mib'])
                    samples += 1
                    if page.locator('#materialOrigin').inner_text().startswith('待確認檔案：' + name):
                        break
                    assert time.monotonic() < deadline, page.locator('#message').inner_text()
                    page.wait_for_timeout(150)
                material = page.locator('#material').input_value()
                parts = re.split(r'【第 (\d+) 頁】', material)
                assert parts[1::2] == [str(n) for n in range(1, 21)], parts[1::2]
                assert all(part.strip() for part in parts[2::2])
                page.locator('#materialForm button').click()
                page.wait_for_function("name => document.querySelector('#materialOrigin').textContent.startsWith('來源：' + name)", arg=name)
                assert not [t for t in targets.send('Target.getTargets')['targetInfos'] if t['type'] == 'worker']
                assert not external, external[:5]
                cdp.send('HeapProfiler.collectGarbage')
                print(json.dumps({'round': index + 1, 'seconds': round(time.monotonic() - started, 2), 'samples': samples, 'sampled_peak_private_mib': peak_private, 'sampled_peak_working_mib': peak_working, 'post_gc': sample()}), flush=True)
            context.close()
            print(json.dumps({'result': 'PASS', 'rounds': rounds, 'bytes': len(payload), 'browser': browser.version}), flush=True)
        finally:
            browser.close()
        print('Browser closed', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rounds', type=int, default=10, choices=range(1, 101))
    run(parser.parse_args().rounds)
