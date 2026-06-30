"""Iris — Windows platform utilities (media app detection, icon extraction, etc.)."""

import logging
import os
import threading
import winreg

log = logging.getLogger("iris.platform")

_MEDIA_CANDIDATES = [
    ("VLC",            "VLC media player",            "vlc.exe"),
    ("AIMP",           "AIMP",                        "AIMP.exe"),
    ("foobar2000",     "foobar2000",                  "foobar2000.exe"),
    ("MPC-HC",         "Media Player Classic Home",   "mpc-hc64.exe"),
    ("MPC-HC",         "Media Player Classic Home",   "mpc-hc.exe"),
    ("MPC-BE",         "MPC-BE",                      "mpc-be64.exe"),
    ("MPC-BE",         "MPC-BE",                      "mpc-be.exe"),
    ("Winamp",         "Winamp",                      "winamp.exe"),
    ("MediaMonkey",    "MediaMonkey",                 "MediaMonkey.exe"),
    ("iTunes",         "iTunes",                      "iTunes.exe"),
    ("Clementine",     "Clementine",                  "clementine.exe"),
    ("Dopamine",       "Dopamine",                    "Dopamine.exe"),
    ("Musicbee",       "MusicBee",                    "MusicBee.exe"),
    ("Strawberry",     "Strawberry",                  "strawberry.exe"),
]

_UNINSTALL_PATHS = [
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
    (winreg.HKEY_CURRENT_USER,  r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
]


def scan_media_apps():
    """Return sorted list of (friendly_name, exe_path) for detected media players."""
    found = {}

    for hive, reg_path in _UNINSTALL_PATHS:
        try:
            key = winreg.OpenKey(hive, reg_path)
        except OSError:
            continue
        count = winreg.QueryInfoKey(key)[0]
        for i in range(count):
            try:
                sub_name = winreg.EnumKey(key, i)
                sub = winreg.OpenKey(key, sub_name)
            except OSError:
                continue
            try:
                display_name = winreg.QueryValueEx(sub, "DisplayName")[0]
            except OSError:
                winreg.CloseKey(sub)
                continue

            for friendly, match, exe in _MEDIA_CANDIDATES:
                if friendly in found:
                    continue
                if match.lower() not in display_name.lower():
                    continue
                candidate = None
                try:
                    loc = winreg.QueryValueEx(sub, "InstallLocation")[0].strip()
                    if loc:
                        candidate = os.path.join(loc, exe)
                except OSError:
                    pass
                if not candidate or not os.path.exists(candidate):
                    try:
                        unins = winreg.QueryValueEx(sub, "UninstallString")[0].strip('"').split('"')[0]
                        if not unins.lower().startswith("msiexec"):
                            candidate = os.path.join(os.path.dirname(unins), exe)
                    except OSError:
                        pass
                if candidate and os.path.exists(candidate):
                    found[friendly] = candidate

            winreg.CloseKey(sub)
        winreg.CloseKey(key)

    appdata      = os.environ.get("APPDATA", "")
    localappdata = os.environ.get("LOCALAPPDATA", "")
    systemroot   = os.environ.get("SystemRoot", r"C:\Windows")

    fixed = [
        ("Spotify",              os.path.join(appdata, "Spotify", "Spotify.exe")),
        ("Spotify",              os.path.join(localappdata, "Spotify", "Spotify.exe")),
        ("iTunes",               r"C:\Program Files\iTunes\iTunes.exe"),
        ("Windows Media Player", r"C:\Program Files\Windows Media Player\wmplayer.exe"),
        ("Windows Media Player", os.path.join(systemroot, "system32", "wmplayer.exe")),
    ]
    for friendly, path in fixed:
        if friendly not in found and os.path.exists(path):
            found[friendly] = path

    winapps_dir = os.path.join(localappdata, "Microsoft", "WindowsApps")
    if os.path.isdir(winapps_dir):
        try:
            for fname in os.listdir(winapps_dir):
                if fname == "Spotify.exe":
                    found.setdefault("Spotify", os.path.join(winapps_dir, fname))
                elif fname == "iTunes.exe":
                    found.setdefault("iTunes", os.path.join(winapps_dir, fname))
                elif fname == "spotify_cli.exe" and "Spotify" not in found:
                    found.setdefault("Spotify", os.path.join(winapps_dir, fname))
        except Exception:
            pass

    return sorted(found.items(), key=lambda x: x[0].lower())


# ── App icon extraction ──────────────────────────────────────────

_icon_cache = {}  # (normpath_lower, size) -> PIL Image


def extract_app_icon(exe_path, size=40):
    """Extract application icon from an .exe / .lnk / .ico as a PIL RGBA Image.

    Uses the Windows shell API to get the large icon associated with the file,
    renders it into a DIB section via DrawIconEx, and returns a PIL Image.
    Results are cached by (path, size) for the lifetime of the process.
    """
    if not exe_path or not os.path.exists(exe_path):
        return None
    key = (os.path.normpath(exe_path).lower(), size)
    if key in _icon_cache:
        return _icon_cache[key]

    import ctypes
    from ctypes import wintypes

    shell32 = ctypes.windll.shell32
    user32  = ctypes.windll.user32
    gdi32   = ctypes.windll.gdi32

    SHGFI_ICON = 0x000000100

    class SHFILEINFOW(ctypes.Structure):
        _fields_ = [
            ("hIcon", wintypes.HANDLE),
            ("iIcon", ctypes.c_int),
            ("dwAttributes", ctypes.c_ulong),
            ("szDisplayName", ctypes.c_wchar * 260),
            ("szTypeName", ctypes.c_wchar * 80),
        ]

    sfi = SHFILEINFOW()
    ret = shell32.SHGetFileInfoW(
        exe_path, 0, ctypes.byref(sfi), ctypes.sizeof(sfi),
        SHGFI_ICON | 0x000000000,  # SHGFI_LARGEICON
    )
    if not ret or not sfi.hIcon:
        return None

    try:
        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize",          wintypes.DWORD),
                ("biWidth",         ctypes.c_long),
                ("biHeight",        ctypes.c_long),
                ("biPlanes",        wintypes.WORD),
                ("biBitCount",      wintypes.WORD),
                ("biCompression",   wintypes.DWORD),
                ("biSizeImage",     wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed",       wintypes.DWORD),
                ("biClrImportant",  wintypes.DWORD),
            ]

        class BITMAPINFO(ctypes.Structure):
            _fields_ = [
                ("bmiHeader", BITMAPINFOHEADER),
            ]

        bmi = BITMAPINFO()
        bmi.bmiHeader.biSize       = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.bmiHeader.biWidth      = size
        bmi.bmiHeader.biHeight     = -size  # top-down
        bmi.bmiHeader.biPlanes     = 1
        bmi.bmiHeader.biBitCount   = 32
        bmi.bmiHeader.biCompression = 0  # BI_RGB

        hdc    = user32.GetDC(None)
        mem_dc = gdi32.CreateCompatibleDC(hdc)

        bits_ptr = ctypes.c_void_p()
        hbmp = gdi32.CreateDIBSection(
            mem_dc, ctypes.byref(bmi), 0, ctypes.byref(bits_ptr), None, 0,
        )
        if not hbmp:
            gdi32.DeleteDC(mem_dc)
            user32.ReleaseDC(None, hdc)
            return None

        gdi32.SelectObject(mem_dc, hbmp)
        user32.DrawIconEx(mem_dc, 0, 0, sfi.hIcon, size, size, 0, None, 0x0003)

        buf_len = size * size * 4
        buf = ctypes.create_string_buffer(buf_len)
        ctypes.memmove(buf, bits_ptr, buf_len)

        gdi32.DeleteObject(hbmp)
        gdi32.DeleteDC(mem_dc)
        user32.ReleaseDC(None, hdc)

        from PIL import Image
        img = Image.frombuffer("RGBA", (size, size), buf, "raw", "BGRA", 0, 1)
        _icon_cache[key] = img
        return img
    finally:
        user32.DestroyIcon(sfi.hIcon)


# ── PowerShell icon extraction (more reliable than shell API) ─────

_file_icon_cache = {}
_PENDING = object()


def _extract_via_ps(path, size):
    """Extract shell icon using PowerShell + System.Drawing (runs in bg thread)."""
    import subprocess, tempfile, shutil
    try:
        from PIL import Image as _PIL
        ps_exe  = shutil.which("pwsh") or "powershell"
        tmp     = tempfile.mktemp(suffix=".png")
        ps_path = path.replace("'", "''")
        tmp_esc = tmp.replace("\\", "\\\\")
        cmd = (
            "Add-Type -AssemblyName System.Drawing; "
            f"$i=[System.Drawing.Icon]::ExtractAssociatedIcon('{ps_path}'); "
            f"if($i){{$b=$i.ToBitmap();$b.Save('{tmp_esc}');$b.Dispose();$i.Dispose()}}"
        )
        subprocess.run(
            [ps_exe, "-NonInteractive", "-NoProfile", "-WindowStyle", "Hidden",
             "-Command", cmd],
            capture_output=True, timeout=12,
        )
        if os.path.exists(tmp):
            img = _PIL.open(tmp).convert("RGBA")
            if img.size != (size, size):
                img = img.resize((size, size), _PIL.LANCZOS)
            img.load()
            try:
                os.unlink(tmp)
            except Exception:
                pass
            return img
    except Exception as exc:
        log.warning("[icon] PS extract failed %r: %s", path, exc)
    return None


def extract_file_icon(path, size, on_done):
    """Request an icon asynchronously via PowerShell.

    Calls on_done(pil_image) when ready — on_done must schedule Tk work
    with widget.after(0, ...) if needed.
    """
    norm = os.path.normpath(path)
    if not os.path.exists(norm):
        return
    key = (norm, size)
    if key in _file_icon_cache:
        cached = _file_icon_cache[key]
        if cached is not _PENDING and cached is not None:
            on_done(cached)
        return
    _file_icon_cache[key] = _PENDING
    def _run():
        result = _extract_via_ps(norm, size)
        _file_icon_cache[key] = result
        if result:
            on_done(result)
    threading.Thread(target=_run, daemon=True).start()
