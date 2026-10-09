"""Low-overhead, on-demand process memory measurements for the Dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
import os
import sys
import tracemalloc


def _read_rss_bytes() -> tuple[int | None, str | None]:
    try:
        import psutil
    except Exception:
        psutil = None
    if psutil is not None:
        try:
            return int(psutil.Process().memory_info().rss), "psutil"
        except Exception:
            pass

    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            class ProcessMemoryCounters(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            current_process = kernel32.GetCurrentProcess
            current_process.restype = wintypes.HANDLE
            get_memory_info = psapi.GetProcessMemoryInfo
            get_memory_info.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessMemoryCounters), wintypes.DWORD]
            get_memory_info.restype = wintypes.BOOL
            counters = ProcessMemoryCounters()
            counters.cb = ctypes.sizeof(counters)
            if get_memory_info(current_process(), ctypes.byref(counters), counters.cb):
                return int(counters.WorkingSetSize), "windows_working_set"
        except Exception:
            pass

    if sys.platform.startswith("linux"):
        try:
            with open("/proc/self/statm", "r", encoding="ascii") as stream:
                resident_pages = int(stream.read().split()[1])
            return resident_pages * int(os.sysconf("SC_PAGE_SIZE")), "proc_statm"
        except (OSError, ValueError, IndexError, TypeError):
            pass
    return None, None


def process_memory_snapshot() -> dict[str, object]:
    """Read current RSS and Python heap only if tracing is already enabled."""
    rss_bytes, rss_source = _read_rss_bytes()
    tracing_active = tracemalloc.is_tracing()
    heap_current_bytes = None
    heap_peak_bytes = None
    if tracing_active:
        try:
            heap_current_bytes, heap_peak_bytes = tracemalloc.get_traced_memory()
        except RuntimeError:
            tracing_active = False

    return {
        "observed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "scope": "astrbot_process",
        "rss_bytes": rss_bytes,
        "rss_source": rss_source,
        "python_tracing_active": tracing_active,
        "python_heap_current_bytes": heap_current_bytes,
        "python_heap_peak_bytes": heap_peak_bytes,
    }
