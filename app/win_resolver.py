"""Iris — audio session / process name resolver.

Turns raw Windows process names (``chrome.exe``, ``QtWebEngineProcess.exe``,
``msedgewebview2.exe``) into friendly display labels, so the volume mixer
reads like the Windows Sound settings instead of a process list.

Resolution priority (first hit wins):

1. Application display name from the audio session (when it is a real name).
2. Parent process name — only for "worker" style executables (``*process.exe``,
   WebView/helper processes) so ``QtWebEngineProcess.exe`` becomes "Chrome".
3. Alias table — curated exact names (``msedge.exe`` -> "Microsoft Edge").
4. Executable version info (FileDescription).
5. Cleaned executable name ("EliteDangerous64" -> "Elite Dangerous 64").
6. Raw executable name as a last resort.
"""

import ctypes
import logging
import os
import re
from functools import lru_cache

log = logging.getLogger("iris.win_resolver")

# ── Curated aliases (exe basename, lowercase -> friendly name) ──────────────
ALIASES = {
    "chrome.exe": "Chrome",
    "msedge.exe": "Microsoft Edge",
    "firefox.exe": "Firefox",
    "brave.exe": "Brave",
    "opera.exe": "Opera",
    "vivaldi.exe": "Vivaldi",
    "notepad.exe": "Notepad",
    "cmd.exe": "Command Prompt",
    "powershell.exe": "PowerShell",
    "windowsterminal.exe": "Windows Terminal",
    "explorer.exe": "Explorer",
    "spotify.exe": "Spotify",
    "discord.exe": "Discord",
    "slack.exe": "Slack",
    "zoom.exe": "Zoom",
    "teams.exe": "Microsoft Teams",
    "vlc.exe": "VLC",
    "itunes.exe": "iTunes",
    "steam.exe": "Steam",
    "epicgameslauncher.exe": "Epic Games",
    "battle.net.exe": "Battle.net",
    "elitedangerous64.exe": "Elite Dangerous",
    "taskmgr.exe": "Task Manager",
    "regedit.exe": "Registry Editor",
    "control.exe": "Control Panel",
    "mspaint.exe": "Paint",
    "winword.exe": "Word",
    "excel.exe": "Excel",
    "powerpnt.exe": "PowerPoint",
    "outlook.exe": "Outlook",
}

# Exe basenames that are child/worker processes -> resolve via their parent.
_WORKER_HINTS = (
    "process.exe",     # QtWebEngineProcess.exe, RuntimeBroker.exe, ...
    "webview",         # msedgewebview2.exe, WebViewHost.exe
    "-process",        # firefox.exe style children (chrome_process)
    "helper",          # chrome_crashpad_handler.exe, ...
    "werfault",
)


def _is_worker(exe_key):
    return any(h in exe_key for h in _WORKER_HINTS)


# ── Name cleaning helpers ───────────────────────────────────────────────────

_EXE_RE = re.compile(r"\.exe$", re.IGNORECASE)
_CAMEL_RE = re.compile(r"([a-z0-9])([A-Z])")
_ACRONYM_RE = re.compile(r"([A-Z]+)([A-Z][a-z])")


def _clean_exe_name(exe_name):
    """'EliteDangerous64.exe' -> 'Elite Dangerous 64'; None if unusable."""
    base = os.path.basename((exe_name or "").strip())
    if not base:
        return None
    base = _EXE_RE.sub("", base)
    spaced = _CAMEL_RE.sub(r"\1 \2", base)
    spaced = _ACRONYM_RE.sub(r"\1 \2", spaced)
    words = [w for w in spaced.split() if w]
    if not words:
        return None
    return " ".join(w[:1].upper() + w[1:] for w in words)


def _nice(name, exe_key):
    """True when *name* is a usable friendly label (not raw/empty)."""
    if not name:
        return False
    name = str(name).strip()
    if not name or len(name) < 2:
        return False
    low = name.lower()
    if low.endswith(".exe"):
        return False
    if exe_key and low == exe_key:
        return False
    return True


def _session_display_name(session):
    """Audio session's own application display name, or None."""
    try:
        if session is None:
            return None
        dn = getattr(session, "DisplayName", None)
        if isinstance(dn, bytes):
            dn = dn.decode("utf-16-le", "ignore").strip("\x00").strip()
        if isinstance(dn, str) and dn.strip():
            return dn.strip()
    except Exception:
        pass
    return None


# ── Executable version info (ctypes, no pywin32 dependency) ─────────────────

@lru_cache(maxsize=512)
def _file_description(path):
    """FileDescription string from the exe version resource, or None."""
    if not path or not os.path.isfile(path):
        return None
    try:
        ver = ctypes.windll.version
        size = ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return None
        ptr = ctypes.c_void_p()
        plen = ctypes.c_uint()
        if not ver.VerQueryValueW(buf, "\\VarFileInfo\\Translation",
                                  ctypes.byref(ptr), ctypes.byref(plen)):
            return None
        trans = ctypes.cast(ptr, ctypes.POINTER(ctypes.c_uint)).contents.value
        lang, codepage = trans & 0xFFFF, trans >> 16
        key = "\\StringFileInfo\\%04x%04x\\FileDescription" % (lang, codepage)
        if not ver.VerQueryValueW(buf, key,
                                  ctypes.byref(ptr), ctypes.byref(plen)):
            return None
        text = ctypes.wstring_at(ptr).rstrip("\x00").strip()
        return text or None
    except Exception as e:
        log.debug("[resolver] version info for %s: %s", path, e)
        return None


# ── Parent process resolution ───────────────────────────────────────────────

_SHELL_NAMES = {"explorer.exe", "cmd.exe", "conhost.exe", "dwm.exe",
                "sihost.exe", "taskhostw.exe", "svchost.exe"}


@lru_cache(maxsize=256)
def _parent_friendly_name(pid):
    """Resolve the parent process of *pid* to a friendly name, or None."""
    try:
        import psutil
        p = psutil.Process(pid)
        parent = p.parent()
        if parent is None or parent.pid == pid:
            return None
        try:
            exe_path = parent.exe()
        except Exception:
            exe_path = None
        exe_name = os.path.basename(exe_path) if exe_path else (parent.name() or "")
        exe_key = exe_name.lower()
        if not exe_name or exe_key in _SHELL_NAMES:
            return None
        return _friendly_for_process(exe_name, exe_path)
    except Exception as e:
        log.debug("[resolver] parent of %s: %s", pid, e)
        return None


@lru_cache(maxsize=512)
def _friendly_for_process(exe_name, exe_path):
    """Friendly name for a bare process (alias/version/cleaned)."""
    exe_key = (exe_name or "").lower()
    alias = ALIASES.get(exe_key)
    if alias:
        return alias
    desc = _file_description(exe_path)
    if _nice(desc, exe_key):
        return desc
    cleaned = _clean_exe_name(exe_name)
    if cleaned:
        return cleaned
    return exe_name or "Application"


# ── Main entry point ────────────────────────────────────────────────────────

def resolve(session=None, pid=None, exe_path=None, exe_name=None):
    """Return {"name": str, "exe": str, "source": str} friendly label.

    ``session`` is an optional pycaw AudioSession (for its display name),
    ``pid`` the session's process id, ``exe_path``/``exe_name`` the resolved
    executable path / basename.  Missing pid info falls back gracefully.
    """
    if exe_name is None:
        if exe_path:
            exe_name = os.path.basename(exe_path)
        elif pid:
            try:
                import psutil
                exe_path = psutil.Process(pid).exe()
                exe_name = os.path.basename(exe_path)
            except Exception:
                exe_name = None
    exe_key = (exe_name or "").lower()

    # 1. Application display name from the audio session.
    disp = _session_display_name(session)
    if _nice(disp, exe_key):
        return {"name": disp, "exe": exe_name, "source": "display"}

    # 2. Parent process name (worker/child executables only).
    if pid is not None and _is_worker(exe_key):
        parent_name = _parent_friendly_name(pid)
        if parent_name and _nice(parent_name, exe_key):
            return {"name": parent_name, "exe": exe_name, "source": "parent"}

    # 3. Curated alias.
    alias = ALIASES.get(exe_key)
    if alias:
        return {"name": alias, "exe": exe_name, "source": "alias"}

    # 4. Executable version info (FileDescription).
    desc = _file_description(exe_path)
    if _nice(desc, exe_key):
        return {"name": desc, "exe": exe_name, "source": "version"}

    # 5. Cleaned executable name.
    cleaned = _clean_exe_name(exe_name)
    if cleaned:
        return {"name": cleaned, "exe": exe_name, "source": "clean"}

    # 6. Raw executable name.
    raw = exe_name or "Application"
    return {"name": raw, "exe": exe_name, "source": "raw"}
