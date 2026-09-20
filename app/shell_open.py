"""Iris — Windows Shell "Open with …" registration.

Registers an "Iris Notes" open-with verb in HKCU (no admin required) so that
Explorer can hand any file to Iris Notes. If Iris is already running, the
launcher forwards the request to the running instance over loopback HTTP;
otherwise it starts Iris and opens the note after boot.

Registry layout (all under HKEY_CURRENT_USER\\Software\\Classes):
  Applications\\IrisNotes\\shell\\open\\command  = "<launcher>" --open-note "%1"
  Applications\\IrisNotes\\FriendlyAppName      = "Iris Notes"
  .txt\\OpenWithProgids\\IrisNotes             = ""   (pins into the .txt Open With list)

The command is re-registered on every Iris startup so it always matches the
current launcher path (frozen exe vs dev interpreter).
"""

import logging
import os
import sys

log = logging.getLogger("iris.shell_open")

_APP_ID = "IrisNotes"
_FRIENDLY = "Iris Notes"
_CMD_KEY = r"Software\Classes\Applications\IrisNotes\shell\open\command"
_APP_KEY = r"Software\Classes\Applications\IrisNotes"
_PROGIDS_KEY = r"Software\Classes\.txt\OpenWithProgids"


def _app_dir():
    return os.path.dirname(os.path.abspath(__file__))


def _launcher_argv():
    """Return the argv prefix that opens an external note.

    Frozen  -> [<Iris.exe>, "--open-note"]
    dist    -> [<dist/Iris.exe>, "--open-note"]   (bundled build next to the tree)
    Dev     -> [<pythonw.exe>, <app>/main.py, "--open-note"]  (no console flash)
    """
    if getattr(sys, "frozen", False):
        return [os.path.abspath(sys.executable), "--open-note"]

    exe = os.path.join(os.path.dirname(_app_dir()), "dist", "Iris.exe")
    # Only trust a prebuilt bundle when it is at least as new as this module —
    # otherwise a stale Iris.exe would boot without --open-note support.
    if os.path.isfile(exe) and os.path.getmtime(exe) >= os.path.getmtime(__file__):
        return [exe, "--open-note"]

    base = os.path.dirname(os.path.abspath(sys.executable))
    pythonw = os.path.join(base, "pythonw.exe")
    if not os.path.isfile(pythonw):
        pythonw = os.path.abspath(sys.executable)
    main_py = os.path.join(_app_dir(), "main.py")
    return [pythonw, main_py, "--open-note"]


def _command():
    parts = _launcher_argv()
    quoted = " ".join('"%s"' % p.replace('"', '\\"') for p in parts)
    return quoted + ' "%1"'


def _delete_key_tree(root, subkey):
    import winreg
    try:
        with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ) as k:
            try:
                for i in range(winreg.QueryInfoKey(k)[0]):
                    _delete_key_tree(root, f"{subkey}\\{winreg.EnumKey(k, i)}")
            except OSError:
                pass
        winreg.DeleteKey(root, subkey)
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning("[shell-open] could not delete key %s: %s", subkey, e)


def set_open_with(enabled=True):
    """(Re)register or remove the Windows 'Open with …' entry for Iris Notes."""
    import winreg
    if not enabled:
        unregister()
        return
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _CMD_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, _command())
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _APP_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, "FriendlyAppName", 0, winreg.REG_SZ, _FRIENDLY)
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, _PROGIDS_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, _APP_ID, 0, winreg.REG_NONE, b"")
        log.info("[shell-open] 'Open with Iris Notes' registered: %s", _command())
    except Exception as e:
        log.warning("[shell-open] failed to register open-with entry: %s", e)


def unregister():
    """Remove the Iris Notes open-with registration."""
    import winreg
    _delete_key_tree(winreg.HKEY_CURRENT_USER, _APP_KEY)
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _PROGIDS_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.DeleteValue(key, _APP_ID)
    except FileNotFoundError:
        pass
    except OSError as e:
        log.warning("[shell-open] could not remove progid %s: %s", _APP_ID, e)
    log.info("[shell-open] 'Open with Iris Notes' unregistered")


def open_with_registered():
    """True when the Iris Notes open-with command is currently registered."""
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _CMD_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, "")
            return True
    except (FileNotFoundError, OSError):
        return False