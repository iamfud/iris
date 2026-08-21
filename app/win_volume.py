"""Iris — per-application volume control via WASAPI.

Matches the foreground application's audio session (the same API the Windows
Volume Mixer uses) and adjusts only that session's volume.  The Iris panel
itself is excluded from targeting, so the slider keeps controlling the last
real foreground app while the panel is focused.
"""

import contextlib
import ctypes
import logging
import os
import sys
import threading
import time

import win_resolver

log = logging.getLogger("iris.volume")


@contextlib.contextmanager
def _com_session():
    import comtypes
    init = False
    try:
        comtypes.CoInitialize()
        init = True
    except Exception:
        pass
    try:
        yield
    finally:
        if init:
            try:
                comtypes.CoUninitialize()
            except Exception:
                pass

# Foreground PIDs of Iris-owned processes are ignored (panel/WebView2/app).
_SELF_NAMES = {
    "msedgewebview2.exe",
    "python.exe",
    "pythonw.exe",
    "iris.exe",
    "irisw.exe",
}

_TARGET_LOCK = threading.Lock()
_target = {"pid": None, "name": None}
_tracker_started = False
_tracker_interval = 0.3


def _is_self_exe(exe_path):
    """Return True if *exe_path* belongs to Iris itself."""
    if not exe_path:
        return True
    exe_path = exe_path.lower()
    name = os.path.basename(exe_path)
    if name in _SELF_NAMES:
        return True
    try:
        app_dir = os.path.dirname(os.path.abspath(__file__)).lower()
        if exe_path.startswith(app_dir):
            return True
        if getattr(sys, "frozen", False):
            bundle_dir = os.path.dirname(os.path.abspath(sys.executable)).lower()
            if exe_path.startswith(bundle_dir):
                return True
    except Exception:
        pass
    return False


def get_foreground_pid():
    """Return the PID of the foreground window, or None."""
    try:
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        return pid.value or None
    except Exception as e:
        log.debug("[volume] get_foreground_pid: %s", e)
        return None


def _refresh_target():
    """Point the volume control at the last non-Iris foreground app."""
    pid = get_foreground_pid()
    if pid is None:
        return
    try:
        import psutil
        exe = psutil.Process(pid).exe()
    except Exception:
        return
    if _is_self_exe(exe):
        return
    with _TARGET_LOCK:
        _target["pid"] = pid
        _target["name"] = os.path.basename(exe)


def _track_foreground():
    """Continuously capture the foreground app while Iris isn't focused.

    The panel is a blacklisted (self) process, so the target must be captured
    *before* the panel steals focus — a background thread keeps it fresh.
    """
    while True:
        try:
            pid = get_foreground_pid()
            if pid is not None:
                try:
                    import psutil
                    exe = psutil.Process(pid).exe()
                except Exception:
                    exe = None
                if not _is_self_exe(exe):
                    with _TARGET_LOCK:
                        _target["pid"] = pid
                        _target["name"] = os.path.basename(exe) if exe else None
        except Exception:
            pass
        time.sleep(_tracker_interval)


def start_tracker():
    """Start the background foreground tracker (idempotent)."""
    global _tracker_started
    if _tracker_started:
        return
    _tracker_started = True
    threading.Thread(target=_track_foreground, daemon=True,
                     name="win-volume-tracker").start()


start_tracker()


def find_session(pid, name=None):
    """Return the pycaw AudioSession for *pid*, or None.

    Matches by PID first; falls back to the single session whose process name
    matches *name* (covers games that route audio through the same exe but a
    different process PID)."""
    if not pid:
        return None
    sessions = []
    try:
        import comtypes
        from pycaw.utils import AudioUtilities
        with _com_session():
            sessions = AudioUtilities.GetAllSessions()
    except Exception as e:
        log.debug("[volume] find_session: %s", e)
        return None

    for session in sessions:
        try:
            if session.ProcessId == pid:
                return session
        except Exception:
            continue

    if name:
        matches = []
        for session in sessions:
            try:
                proc = session.Process
                if proc is not None and proc.name().lower() == name.lower():
                    matches.append(session)
            except Exception:
                continue
        if len(matches) == 1:
            return matches[0]
    return None


def get_active_app_state():
    """Return {"app": <friendly name or None>, "volume": <int 0-100 or None>}."""
    _refresh_target()
    with _TARGET_LOCK:
        pid = _target["pid"]
        name = _target["name"]
    if pid is None:
        return {"app": None, "volume": None}
    session = find_session(pid, name)
    exe_path = _exe_path_for(pid)
    resolved = win_resolver.resolve(session=session, pid=pid,
                                    exe_path=exe_path, exe_name=name)
    friendly = resolved["name"]
    if session is None:
        return {"app": friendly, "volume": None}
    try:
        sav = session.SimpleAudioVolume
        if sav is None:
            return {"app": friendly, "volume": None}
        return {"app": friendly, "volume": round(sav.GetMasterVolume() * 100)}
    except Exception as e:
        log.debug("[volume] get volume: %s", e)
        return {"app": friendly, "volume": None}


def set_active_app_volume(value):
    """Set the active app's session volume (0-100). No-op without a session.

    Returns True on success, False if there is no session (caller should do
    nothing in that case).
    """
    _refresh_target()
    with _TARGET_LOCK:
        pid = _target["pid"]
        name = _target["name"]
    if pid is None:
        return False
    session = find_session(pid, name)
    if session is None:
        return False
    try:
        sav = session.SimpleAudioVolume
        if sav is None:
            return False
        sav.SetMasterVolume(max(0.0, min(1.0, value / 100.0)), None)
        return True
    except Exception as e:
        log.debug("[volume] set volume: %s", e)
        return False


def list_sessions():
    """Return all open render audio sessions (skipping Iris/self + expired).

    Each dict: {"pid": int, "name": str, "volume": int 0-100 | None,
    "mute": bool | None, "active": bool}.  ``name`` is the friendly display
    name from win_resolver (e.g. "Chrome" for chrome.exe).  ``active`` is
    True when the session's State is Active, i.e. the app is audibly playing
    right now.
    """
    sessions = []
    try:
        import comtypes
        from pycaw.utils import AudioUtilities
        from pycaw.constants import AudioSessionState
        with _com_session():
            all_sessions = AudioUtilities.GetAllSessions()
    except Exception as e:
        log.debug("[volume] list_sessions enumerate: %s", e)
        return sessions

    for s in all_sessions:
        try:
            pid = s.ProcessId
            if not pid or _is_self_pid(pid):
                continue
            if getattr(s, "State", None) == AudioSessionState.Expired:
                continue
            exe_path = _exe_path_for(pid)
            name = win_resolver.resolve(
                session=s, pid=pid, exe_path=exe_path,
                exe_name=os.path.basename(exe_path) if exe_path else None,
            )["name"]
            vol, mute = None, None
            active = False
            try:
                state = s.State
                active = (state == AudioSessionState.Active)
            except Exception:
                pass
            try:
                sav = s.SimpleAudioVolume
                if sav is not None:
                    vol = round(sav.GetMasterVolume() * 100)
                    mute = bool(sav.GetMute())
            except Exception:
                pass
            sessions.append({
                "pid": pid,
                "name": name,
                "exe": os.path.basename(exe_path) if exe_path else None,
                "volume": vol,
                "mute": mute,
                "active": active,
            })
        except Exception:
            continue
    return sessions


def _exe_path_for(pid):
    """Executable path for a pid (best-effort), or None."""
    if not pid:
        return None
    try:
        import psutil
        return psutil.Process(pid).exe()
    except Exception:
        return None


def _is_self_pid(pid):
    """Return True if *pid* belongs to an Iris-owned process."""
    if not pid:
        return False
    try:
        import psutil
        exe = psutil.Process(pid).exe()
    except Exception:
        return False
    return _is_self_exe(exe)


def _find_session_by_pid(pid):
    """Return the pycaw AudioSession for *pid*, or None."""
    if not pid:
        return None
    try:
        import comtypes
        from pycaw.utils import AudioUtilities
        with _com_session():
            for s in AudioUtilities.GetAllSessions():
                try:
                    if s.ProcessId == pid:
                        return s
                except Exception:
                    continue
    except Exception as e:
        log.debug("[volume] find_session_by_pid: %s", e)
    return None


def set_session_volume(pid, value):
    """Set a specific session's volume (0-100). Returns True/False."""
    session = _find_session_by_pid(pid)
    if session is None:
        return False
    try:
        sav = session.SimpleAudioVolume
        if sav is None:
            return False
        sav.SetMasterVolume(max(0.0, min(1.0, value / 100.0)), None)
        return True
    except Exception as e:
        log.debug("[volume] set session volume: %s", e)
        return False


def set_session_mute(pid, mute):
    """Mute/unmute a specific session. Returns True/False."""
    session = _find_session_by_pid(pid)
    if session is None:
        return False
    try:
        sav = session.SimpleAudioVolume
        if sav is None:
            return False
        sav.SetMute(bool(mute), None)
        return True
    except Exception as e:
        log.debug("[volume] set session mute: %s", e)
        return False


def get_master_state():
    """Return {"volume": <int 0-100 or None>} for the default render device."""
    try:
        import comtypes
        from pycaw.utils import AudioUtilities
        with _com_session():
            speakers = AudioUtilities.GetSpeakers()
            if speakers is None:
                return {"volume": None}
            epv = speakers.EndpointVolume
            if epv is None:
                return {"volume": None}
            return {"volume": round(epv.GetMasterVolumeLevelScalar() * 100)}
    except Exception as e:
        log.debug("[volume] get master: %s", e)
        return {"volume": None}


def set_master_volume(value):
    """Set the default render device volume (0-100). Returns True/False."""
    try:
        import comtypes
        from pycaw.utils import AudioUtilities
        with _com_session():
            speakers = AudioUtilities.GetSpeakers()
            if speakers is None:
                return False
            epv = speakers.EndpointVolume
            if epv is None:
                return False
            epv.SetMasterVolumeLevelScalar(max(0.0, min(1.0, value / 100.0)), None)
            return True
    except Exception as e:
        log.debug("[volume] set master: %s", e)
        return False
