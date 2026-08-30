"""Iris — run-at-startup management (Windows RUN registry key)."""

import logging
import os
import sys

log = logging.getLogger("iris.startup")

# RUN key under HKCU (no admin needed; matches per-user install)
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_RUN_NAME = "Iris"


def _exe_path():
    """Absolute path to the Iris executable (or a dev fallback)."""
    if getattr(sys, "frozen", False):
        return os.path.abspath(sys.executable)
    # Dev mode: point at the bundled/frozen Iris.exe if present next to the
    # source tree, else the python interpreter running app/main.py.
    exe = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "dist", "Iris.exe")
    if os.path.isfile(exe):
        return exe
    return os.path.abspath(sys.executable)


def set_startup(enabled):
    """Enable/disable Iris at Windows logon by editing the HKCU Run key.

    Returns True on success, False if the registry could not be updated.
    """
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                winreg.SetValueEx(key, _RUN_NAME, 0, winreg.REG_SZ, f'"{_exe_path()}"')
                log.info("Run-at-startup ENABLED (%s)", _exe_path())
            else:
                try:
                    winreg.DeleteValue(key, _RUN_NAME)
                    log.info("Run-at-startup DISABLED")
                except FileNotFoundError:
                    pass
        return True
    except Exception as e:
        log.warning("Failed to update run-at-startup registry: %s", e)
        return False


def startup_enabled():
    """True if the Iris Run value currently exists."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _RUN_NAME)
            return True
    except FileNotFoundError:
        return False
    except Exception:
        return False
