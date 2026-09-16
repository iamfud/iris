"""Telemetry binary and DLL path resolvers."""

import os
import sys


def get_lib_dir() -> str:
    """Return the absolute path to the directory containing telemetry helper binaries/DLLs."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    else:
        # app/telemetry/paths.py -> app/telemetry -> app -> root
        base = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    return os.path.join(base, "lib")


def get_lhm_dll_path() -> str:
    return os.path.join(get_lib_dir(), "LibreHardwareMonitorLib.dll")


def get_presentmon_exe_path() -> str:
    return os.path.join(get_lib_dir(), "PresentMon-x64.exe")
