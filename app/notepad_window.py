"""HTML Notepad Window — Dedicated pywebview window.

Opens the Iris Note interface in a clean, dedicated 400x500 native window
matching the exact HTML/CSS styling of the Settings panel and Edit Action modal.
"""

import ctypes
import logging
import multiprocessing
import os
import urllib.parse
from ctypes import wintypes

log = logging.getLogger("iris.notepad_window")

_DEFAULT_WIDTH = 400
_DEFAULT_HEIGHT = 500
_MIN_WIDTH = 320
_MIN_HEIGHT = 380

_proc = None


class _NotepadApi:
    """Exposed to JavaScript as window.pywebview.api."""

    def __init__(self, state):
        self._window = None
        self._state = state

    def close_window(self):
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass


def _virtual_screen_bounds():
    SM_XVIRTUALSCREEN = 76
    SM_YVIRTUALSCREEN = 77
    SM_CXVIRTUALSCREEN = 78
    SM_CYVIRTUALSCREEN = 79
    u = ctypes.windll.user32
    return (
        u.GetSystemMetrics(SM_XVIRTUALSCREEN),
        u.GetSystemMetrics(SM_YVIRTUALSCREEN),
        u.GetSystemMetrics(SM_CXVIRTUALSCREEN),
        u.GetSystemMetrics(SM_CYVIRTUALSCREEN),
    )


def _default_position(width, height):
    try:
        user32 = ctypes.windll.user32
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        import vision
        m = vision.monitor_containing(pt.x, pt.y)
        x = m["x"] + (m["w"] - width) // 2
        y = m["y"] + (m["h"] - height) // 3
        return x, y
    except Exception:
        return 150, 150


def _clamp_to_screen(x, y, width, height):
    try:
        sx, sy, sw, sh = _virtual_screen_bounds()
        x = max(sx - width + 100, min(x, sx + sw - 100))
        y = max(sy, min(y, sy + sh - 100))
        return int(x), int(y)
    except Exception:
        return int(x), int(y)


def _apply_dark_title_bar(hwnd):
    if not hwnd:
        return
    try:
        dwm = ctypes.windll.dwmapi
        user32 = ctypes.windll.user32
        parent = user32.GetParent(hwnd)
        target_hwnds = [h for h in (parent, hwnd) if h]

        for h in target_hwnds:
            # 1. DWMWA_USE_IMMERSIVE_DARK_MODE = 20
            dwm.DwmSetWindowAttribute(
                h, 20,
                ctypes.byref(ctypes.c_int(1)),
                ctypes.sizeof(ctypes.c_int),
            )
            # 2. DWMWA_CAPTION_COLOR = 35 (#0B0F12 -> 0x00120F0B)
            dwm.DwmSetWindowAttribute(
                h, 35,
                ctypes.byref(ctypes.c_int(0x00120F0B)),
                ctypes.sizeof(ctypes.c_int),
            )
            # 3. DWMWA_TEXT_COLOR = 36 (#E6E9ED -> 0x00EDE9E6)
            dwm.DwmSetWindowAttribute(
                h, 36,
                ctypes.byref(ctypes.c_int(0x00EDE9E6)),
                ctypes.sizeof(ctypes.c_int),
            )
            # 4. DWMWA_BORDER_COLOR = 34 (#252C34 -> 0x00342C25)
            dwm.DwmSetWindowAttribute(
                h, 34,
                ctypes.byref(ctypes.c_int(0x00342C25)),
                ctypes.sizeof(ctypes.c_int),
            )
    except Exception:
        pass


def _save_geometry(state):
    try:
        x = state.get("x")
        y = state.get("y")
        width = state.get("width")
        height = state.get("height")
        if x is None or y is None:
            return
        x, y = _clamp_to_screen(int(x), int(y), int(width), int(height))
        from config import load_config, save_config
        cfg = load_config()
        cfg["notepad_geometry"] = {"x": x, "y": y, "w": int(width), "h": int(height)}
        save_config(cfg)
    except Exception as e:
        log.warning("[notepad_window] failed to save position: %s", e)


def _find_windows_for_pid(pid: int) -> list:
    if not pid:
        return []
    user32 = ctypes.windll.user32
    hwnds = []

    def enum_cb(hwnd, _):
        if not user32.IsWindow(hwnd):
            return True
        lp_pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
        if lp_pid.value == pid:
            buf = ctypes.create_unicode_buffer(256)
            user32.GetClassNameW(hwnd, buf, 256)
            cname = buf.value or ""
            if any(ign in cname for ign in ("GDI+", ".NET", "MSCTFIME", "Default IME", "Message")):
                return True
            hwnds.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    cb = WNDENUMPROC(enum_cb)
    try:
        user32.EnumWindows(cb, 0)
    except Exception:
        pass
    return hwnds


def _bring_to_foreground(hwnd):
    if not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass


def _run(width, height, x=None, y=None, app_tag="general", filename=None, initial_title=None, initial_body=None):
    try:
        from win_platform import init_dpi_awareness
        init_dpi_awareness()
    except Exception:
        pass

    try:
        import os
        import paths
        wv_data = paths.get_webview_data_dir("WebView2_Notepad")
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = wv_data
        safe_args = "--disable-gpu-compositing --disable-direct-composition"
        existing = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
        if safe_args not in existing:
            os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"{existing} {safe_args}".strip()
    except Exception:
        pass

    try:
        import webview
    except ImportError:
        print("[notepad_window] pywebview not installed")
        return

    import time

    state = {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "ready": False,
    }

    api = _NotepadApi(state)
    
    q_params = {"view": "notepad", "_t": int(time.time())}
    if app_tag:
        q_params["app"] = str(app_tag)
    if filename:
        q_params["file"] = str(filename)
    if initial_title:
        q_params["title"] = str(initial_title)
    if initial_body:
        q_params["body"] = str(initial_body)
    
    qs = urllib.parse.urlencode(q_params)
    note_url = f"http://127.0.0.1:15502/index.html?{qs}"

    if x is None or y is None:
        x, y = _default_position(width, height)
    if x is not None and y is not None:
        x, y = _clamp_to_screen(x, y, width, height)

    state["x"] = x
    state["y"] = y

    create_kwargs = {
        "width": width,
        "height": height,
        "x": x,
        "y": y,
        "frameless": False,
        "easy_drag": False,
        "background_color": "#14171d",
        "js_api": api,
        "min_size": (_MIN_WIDTH, _MIN_HEIGHT),
    }

    title = f"Iris Note · {app_tag.upper()}" if app_tag and app_tag != "general" else "Iris Note"
    w = webview.create_window(title, note_url, **create_kwargs)
    api._window = w

    def _on_moved(mx, my):
        if not state["ready"]:
            return
        try:
            state["x"] = int(mx)
            state["y"] = int(my)
        except Exception:
            pass

    def _on_resized(rw, rh):
        if not state["ready"]:
            return
        try:
            state["width"] = int(rw)
            state["height"] = int(rh)
        except Exception:
            pass

    def _on_shown():
        state["ready"] = True
        try:
            hwnd = None
            if w.gui is not None:
                hwnd = getattr(w.gui, "hwnd", None)
            if not hwnd:
                hwnds = _find_windows_for_pid(os.getpid())
                if hwnds:
                    hwnd = hwnds[0]
            if hwnd:
                _apply_dark_title_bar(hwnd)
        except Exception:
            pass

    def _on_closing():
        _save_geometry(state)

    w.events.moved += _on_moved
    w.events.resized += _on_resized
    w.events.shown += _on_shown
    w.events.closing += _on_closing

    webview.start(debug=False)
    _save_geometry(state)


def open_notepad(app_tag="general", filename=None, initial_title=None, initial_body=None):
    """Open the dedicated HTML Notepad desktop window."""
    global _proc

    if _proc is not None and _proc.is_alive():
        if initial_body or initial_title or filename:
            # If new content or a specific file is requested, restart notepad to display it
            close_notepad()
        else:
            hwnds = _find_windows_for_pid(_proc.pid)
            if hwnds:
                for hwnd in hwnds:
                    _bring_to_foreground(hwnd)
                log.info("[notepad_window] brought existing notepad to foreground (pid=%d)", _proc.pid)
                return
            else:
                close_notepad()

    try:
        from config import load_config
        cfg = load_config()
        geom = cfg.get("notepad_geometry") or {}
        x = geom.get("x")
        y = geom.get("y")
        w = geom.get("w", _DEFAULT_WIDTH)
        h = geom.get("h", _DEFAULT_HEIGHT)
    except Exception:
        x = y = None
        w, h = _DEFAULT_WIDTH, _DEFAULT_HEIGHT

    try:
        w = int(w) if w else _DEFAULT_WIDTH
        h = int(h) if h else _DEFAULT_HEIGHT
        x = int(x) if x is not None else None
        y = int(y) if y is not None else None
    except Exception:
        w, h = _DEFAULT_WIDTH, _DEFAULT_HEIGHT
        x = y = None

    _proc = multiprocessing.Process(
        target=_run, args=(w, h, x, y, app_tag, filename, initial_title, initial_body), daemon=True, name="notepad_window"
    )
    _proc.start()
    log.info("[notepad_window] process started (pid=%d)", _proc.pid)


def is_notepad_open():
    """Return True if the dedicated notepad window is running."""
    global _proc
    return _proc is not None and _proc.is_alive()


def close_notepad():
    """Close the dedicated notepad window if open."""
    global _proc
    if _proc is not None and _proc.is_alive():
        _proc.terminate()
        _proc.join(timeout=1)
    _proc = None
