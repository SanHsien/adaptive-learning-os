"""Opt-in Windows resource smoke for a real, locally synthesized Whisper workload.

Outputs only process measurements. The synthetic media and transcript are temporary.
"""

import argparse
import ctypes
import json
import os
import subprocess
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

from local_server import ROOT, launch_worker, stop_process_tree
from real_whisper_inference_cancel_smoke import synthetic_audio


class ProcessMemoryCounters(ctypes.Structure):
    _fields_ = [('cb', wintypes.DWORD), ('PageFaultCount', wintypes.DWORD),
                ('PeakWorkingSetSize', ctypes.c_size_t), ('WorkingSetSize', ctypes.c_size_t),
                ('QuotaPeakPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPagedPoolUsage', ctypes.c_size_t),
                ('QuotaPeakNonPagedPoolUsage', ctypes.c_size_t),
                ('QuotaNonPagedPoolUsage', ctypes.c_size_t),
                ('PagefileUsage', ctypes.c_size_t), ('PeakPagefileUsage', ctypes.c_size_t)]


class ProcessEntry(ctypes.Structure):
    _fields_ = [('dwSize', wintypes.DWORD), ('cntUsage', wintypes.DWORD),
                ('th32ProcessID', wintypes.DWORD), ('th32DefaultHeapID', ctypes.c_size_t),
                ('th32ModuleID', wintypes.DWORD), ('cntThreads', wintypes.DWORD),
                ('th32ParentProcessID', wintypes.DWORD), ('pcPriClassBase', wintypes.LONG),
                ('dwFlags', wintypes.DWORD), ('szExeFile', wintypes.WCHAR * 260)]


def descendant_pids(root_pid):
    kernel = ctypes.windll.kernel32
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    snapshot = kernel.CreateToolhelp32Snapshot(0x2, 0)
    if snapshot == ctypes.c_void_p(-1).value:
        raise ctypes.WinError()
    try:
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(entry)
        children = {}
        if kernel.Process32FirstW(snapshot, ctypes.byref(entry)):
            while True:
                children.setdefault(entry.th32ParentProcessID, []).append(entry.th32ProcessID)
                if not kernel.Process32NextW(snapshot, ctypes.byref(entry)):
                    break
        found = [root_pid]
        for pid in found:
            found.extend(child for child in children.get(pid, ()) if child not in found)
        return found
    finally:
        kernel.CloseHandle(snapshot)


def process_memory_bytes(handle):
    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    success = ctypes.windll.psapi.GetProcessMemoryInfo(
        handle, ctypes.byref(counters), counters.cb)
    if not success:
        raise ctypes.WinError()
    return counters.WorkingSetSize


def process_cpu_seconds(handle):
    created, exited, kernel, user = (wintypes.FILETIME() for _ in range(4))
    success = ctypes.windll.kernel32.GetProcessTimes(
        handle, ctypes.byref(created), ctypes.byref(exited),
        ctypes.byref(kernel), ctypes.byref(user))
    if not success:
        raise ctypes.WinError()

    def seconds(value):
        return ((value.dwHighDateTime << 32) | value.dwLowDateTime) / 10_000_000

    return seconds(kernel) + seconds(user)


def sample_process_tree(root_pid, cpu_by_pid):
    kernel = ctypes.windll.kernel32
    kernel.OpenProcess.restype = wintypes.HANDLE
    memory = 0
    count = 0
    for pid in descendant_pids(root_pid):
        handle = kernel.OpenProcess(0x1000 | 0x10, False, pid)
        if not handle:
            continue  # The process may exit between snapshot and opening.
        try:
            try:
                memory += process_memory_bytes(handle)
                cpu_by_pid[pid] = max(cpu_by_pid.get(pid, 0), process_cpu_seconds(handle))
                count += 1
            except OSError:
                pass  # Process raced with sampler.
        finally:
            kernel.CloseHandle(handle)
    return memory, count


def main():
    parser = argparse.ArgumentParser(description='Sample real Whisper process-tree resources')
    parser.add_argument('--duration-seconds', type=int, default=45, choices=range(30, 181), metavar='30..180')
    options = parser.parse_args()
    if os.name != 'nt':
        raise RuntimeError('Windows process counters required')
    interpreter = ROOT / '.venv' / 'Scripts' / 'python.exe'
    if not interpreter.is_file():
        raise RuntimeError('Project .venv with faster-whisper is required')
    with tempfile.TemporaryDirectory(prefix='adaptive-whisper-resource-') as directory:
        source = Path(directory) / 'synthetic.wav'
        target = Path(directory) / 'output.srt'
        synthetic_audio(source, options.duration_seconds)
        command = [str(interpreter), str(ROOT / 'tools' / 'transcribe_local.py'),
                   str(source), '--output', str(target), '--model', 'small']
        process = launch_worker(command)
        start = time.monotonic()
        peak_bytes = 0
        peak_processes = 0
        cpu_by_pid = {}
        samples = 0
        try:
            while process.poll() is None:
                if time.monotonic() - start > max(180, options.duration_seconds * 4):
                    raise TimeoutError('Whisper transcription exceeded the bounded runtime')
                memory_bytes, count = sample_process_tree(process.pid, cpu_by_pid)
                peak_bytes = max(peak_bytes, memory_bytes)
                peak_processes = max(peak_processes, count)
                samples += 1
                time.sleep(.25)
            _, error = process.communicate(timeout=15)
            sample_process_tree(process.pid, cpu_by_pid)
            assert process.returncode == 0, f'Whisper exited with {process.returncode}: {error[-400:]!r}'
            assert target.is_file() and target.stat().st_size > 0, 'No SRT produced'
            print(json.dumps({
                'result': 'PASS', 'workload': 'synthetic repeated Chinese speech',
                'requested_audio_seconds': options.duration_seconds,
                'wall_seconds': round(time.monotonic() - start, 2),
                'sampled_process_tree_cpu_seconds': round(sum(cpu_by_pid.values()), 2),
                'sampled_peak_tree_working_set_mib': round(peak_bytes / 1048576, 1),
                'max_sampled_processes': peak_processes,
                'samples': samples,
            }, ensure_ascii=False), flush=True)
        finally:
            stop_process_tree(process)
            process.communicate(timeout=15)


if __name__ == '__main__':
    main()
