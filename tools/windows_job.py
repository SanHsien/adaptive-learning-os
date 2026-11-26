"""Windows Job Object lifetime management for local transcription workers."""

import ctypes
from ctypes import wintypes

JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
JOB_OBJECT_LIMIT_ACTIVE_PROCESS = 0x8
JOB_OBJECT_LIMIT_JOB_MEMORY = 0x200
JOB_MEMORY_BYTES = 4 * 1024**3
JOB_ACTIVE_PROCESSES = 8
JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS = 9


class LARGE_INTEGER(ctypes.Structure):
    _fields_ = [('QuadPart', ctypes.c_longlong)]


class BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [('PerProcessUserTimeLimit', LARGE_INTEGER),
                ('PerJobUserTimeLimit', LARGE_INTEGER),
                ('LimitFlags', wintypes.DWORD),
                ('MinimumWorkingSetSize', ctypes.c_size_t),
                ('MaximumWorkingSetSize', ctypes.c_size_t),
                ('ActiveProcessLimit', wintypes.DWORD),
                ('Affinity', ctypes.c_size_t),
                ('PriorityClass', wintypes.DWORD),
                ('SchedulingClass', wintypes.DWORD)]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_ulonglong) for name in (
        'ReadOperationCount', 'WriteOperationCount', 'OtherOperationCount',
        'ReadTransferCount', 'WriteTransferCount', 'OtherTransferCount')]


class EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [('BasicLimitInformation', BASIC_LIMIT_INFORMATION),
                ('IoInfo', IO_COUNTERS),
                ('ProcessMemoryLimit', ctypes.c_size_t),
                ('JobMemoryLimit', ctypes.c_size_t),
                ('PeakProcessMemoryUsed', ctypes.c_size_t),
                ('PeakJobMemoryUsed', ctypes.c_size_t)]


kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
kernel32.CreateJobObjectW.argtypes = (wintypes.LPVOID, wintypes.LPCWSTR)
kernel32.CreateJobObjectW.restype = wintypes.HANDLE
kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD)
kernel32.SetInformationJobObject.restype = wintypes.BOOL
kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
kernel32.CloseHandle.restype = wintypes.BOOL

ntdll = ctypes.WinDLL('ntdll', use_last_error=True)
ntdll.NtResumeProcess.argtypes = (wintypes.HANDLE,)
ntdll.NtResumeProcess.restype = ctypes.c_long


def attach_job(process, *, memory_bytes=JOB_MEMORY_BYTES, active_processes=JOB_ACTIVE_PROCESSES):
    """Own this worker's descendant group until the returned handle is closed."""
    handle = kernel32.CreateJobObjectW(None, None)
    if not handle:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        limits = EXTENDED_LIMIT_INFORMATION()
        limits.BasicLimitInformation.LimitFlags = (JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
                                                    | JOB_OBJECT_LIMIT_ACTIVE_PROCESS
                                                    | JOB_OBJECT_LIMIT_JOB_MEMORY)
        limits.BasicLimitInformation.ActiveProcessLimit = active_processes
        limits.JobMemoryLimit = memory_bytes
        if not kernel32.SetInformationJobObject(handle, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION_CLASS,
                                                ctypes.byref(limits), ctypes.sizeof(limits)):
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel32.AssignProcessToJobObject(handle, int(process._handle)):
            raise ctypes.WinError(ctypes.get_last_error())
    except BaseException:
        kernel32.CloseHandle(handle)
        raise
    return handle


def close_job(handle):
    if handle:
        kernel32.CloseHandle(handle)


def resume_process(process):
    """Resume a process created suspended, after its Job assignment succeeds."""
    status = ntdll.NtResumeProcess(int(process._handle))
    if status != 0:
        raise OSError(f'NtResumeProcess failed with NTSTATUS 0x{status & 0xffffffff:08x}')
