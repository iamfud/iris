"""HTML settings panel — pywebview frameless wrapper.

Opens the settings HTML UI in a native window with no browser chrome.
Uses multiprocessing so pywebview gets its own main thread (required by Edge/WebView2 on Windows).
HTML and API both load from the local HTTP bridge (same-origin) so no CORS is needed.
"""

import ctypes
import logging
import multiprocessing

log = logging.getLogger("iris.panel")

_DEFAULT_WIDTH = 950
_DEFAULT_HEIGHT = 680
_MIN_WIDTH = 800
_MIN_HEIGHT = 560

_proc = None


class _JSApi:
    """Exposed to JavaScript as window.pywebview.api."""

    def __init__(self, state):
        self._window = None
        self._state = state

    def move_window(self, dx, dy):
        if not self._window:
            return
        try:
            x = self._state["x"]
            y = self._state["y"]
            if x is None or y is None:
                return
            nx = int(x + dx)
            ny = int(y + dy)
            self._window.move(nx, ny)
            self._state["x"] = nx
            self._state["y"] = ny
        except Exception:
            pass

    def close_panel(self):
        if self._window:
            self._window.destroy()

    def hide_panel(self):
        if self._window:
            try:
                self._window.hide()
            except Exception:
                pass

    def show_panel(self):
        if self._window:
            try:
                self._window.show()
            except Exception:
                pass


def _find_windows_for_pid(pid: int) -> list:
    """Find visible top-level window handles owned by process pid."""
    user32 = ctypes.windll.user32
    hwnds = []

    def enum_cb(hwnd, _):
        if not user32.IsWindow(hwnd) or not user32.IsWindowVisible(hwnd):
            return True
        lp_pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
        if lp_pid.value == pid:
            hwnds.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    cb = WNDENUMPROC(enum_cb)
    try:
        user32.EnumWindows(cb, 0)
    except Exception as ex:
        log.warning("[panel] EnumWindows failed: %s", ex)

    # Fallback by window title if none found by PID
    if not hwnds:
        h = user32.FindWindowW(None, "Iris")
        if h and user32.IsWindow(h):
            hwnds.append(h)

    return hwnds


def _bring_to_foreground(hwnd):
    """Restore and bring window to the top of the foreground."""
    if not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        SW_RESTORE = 9
        SW_SHOW = 5
        HWND_TOPMOST = -1
        HWND_NOTOPMOST = -2
        SWP_NOMOVE = 0x0002
        SWP_NOSIZE = 0x0001
        SWP_SHOWWINDOW = 0x0040

        # 1. Unminimize if minimized
        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        # 2. Briefly pulse topmost to pop above background windows
        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

        # 3. Attach thread input to bypass Windows foreground restriction
        fg_hwnd = user32.GetForegroundWindow()
        fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
        cur_thread = kernel32.GetCurrentThreadId()

        if fg_thread and fg_thread != cur_thread:
            user32.AttachThreadInput(cur_thread, fg_thread, True)
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)
            user32.AttachThreadInput(cur_thread, fg_thread, False)
        else:
            user32.BringWindowToTop(hwnd)
            user32.SetForegroundWindow(hwnd)

        # 4. Windows shell activation fallback
        try:
            user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass
    except Exception as ex:
        log.warning("[panel] _bring_to_foreground failed: %s", ex)


def open_panel(width=_DEFAULT_WIDTH, height=_DEFAULT_HEIGHT):
    """Open the settings panel. If already open, brings the existing window to the foreground."""
    global _proc

    if _proc is not None and _proc.is_alive():
        hwnds = _find_windows_for_pid(_proc.pid)
        if hwnds:
            for hwnd in hwnds:
                _bring_to_foreground(hwnd)
            log.info("[panel] brought existing window to foreground (pid=%d)", _proc.pid)
            return
        else:
            # Process alive but window was closed/stale
            log.info("[panel] process %d has no visible window; restarting", _proc.pid)
            close_panel()

    try:
        from config import load_config
        cfg = load_config()
        x = cfg.get("panel_window_x")
        y = cfg.get("panel_window_y")
        w = int(cfg.get("panel_window_width") or width)
        h = int(cfg.get("panel_window_height") or height)
    except Exception:
        x = y = None
        w, h = width, height

    # Discard invalid/corrupt saved geometry.
    if not _valid_size(w, h):
        w, h = width, height
    if x is not None and y is not None:
        try:
            x, y = int(x), int(y)
        except (TypeError, ValueError):
            x = y = None

    _proc = multiprocessing.Process(
        target=_run, args=(w, h, x, y), daemon=True, name="panel"
    )
    _proc.start()
    log.info("[panel] process started (pid=%d)", _proc.pid)



def close_panel():
    """Close the panel if open."""
    global _proc
    if _proc is not None and _proc.is_alive():
        _proc.terminate()
        _proc.join(timeout=2)
    _proc = None


def _valid_size(width, height):
    try:
        return (
            width is not None
            and height is not None
            and int(width) >= _MIN_WIDTH
            and int(height) >= _MIN_HEIGHT
            and int(width) <= 4000
            and int(height) <= 3000
        )
    except (TypeError, ValueError):
        return False


def _virtual_screen_bounds():
    """Return (x, y, width, height) of the virtual screen across all monitors."""
    try:
        user32 = ctypes.windll.user32
        return (
            user32.GetSystemMetrics(76),  # SM_XVIRTUALSCREEN
            user32.GetSystemMetrics(77),  # SM_YVIRTUALSCREEN
            user32.GetSystemMetrics(78),  # SM_CXVIRTUALSCREEN
            user32.GetSystemMetrics(79),  # SM_CYVIRTUALSCREEN
        )
    except Exception:
        return (0, 0, 1920, 1080)


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", ctypes.c_ulong),
    ]


def _default_position(width, height):
    """Bottom-right of the primary monitor's work area (above the taskbar).

    Used only on first launch; once the user moves the panel, the position is
    remembered in config.
    """
    try:
        user32 = ctypes.windll.user32
        monitor = user32.MonitorFromPoint(0, 0, 2)  # MONITOR_DEFAULTTONEAREST
        info = _MONITORINFO()
        info.cbSize = ctypes.sizeof(_MONITORINFO)
        if not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            return None, None
        margin = 16
        x = info.rcWork.right - width - margin
        y = info.rcWork.bottom - height - margin
        return int(x), int(y)
    except Exception:
        return None, None


def _clamp_to_screen(x, y, width, height):
    """Keep the window at least 100x100 pixels on screen."""
    try:
        sx, sy, sw, sh = _virtual_screen_bounds()
        x = max(sx - width + 100, min(x, sx + sw - 100))
        y = max(sy, min(y, sy + sh - 100))
        return int(x), int(y)
    except Exception:
        return int(x), int(y)


def _save_geometry(state):
    """Persist last known good geometry. Never reads w.x/w.y (those block 15s)."""
    try:
        x = state.get("x")
        y = state.get("y")
        width = state.get("width")
        height = state.get("height")
        if x is None or y is None:
            return
        if not _valid_size(width, height):
            return
        x, y = _clamp_to_screen(int(x), int(y), int(width), int(height))
        from config import load_config, save_config
        cfg = load_config()
        cfg["panel_window_x"] = x
        cfg["panel_window_y"] = y
        cfg["panel_window_width"] = int(width)
        cfg["panel_window_height"] = int(height)
        save_config(cfg)
    except Exception as e:
        print("[panel] failed to save window position:", e)


def _run(width, height, x=None, y=None):
    try:
        import webview
    except ImportError:
        print("[panel] pywebview not installed — pip install pywebview")
        return

    # Track geometry from events — never use w.x/w.y/w.width/w.height
    # (those call shown.wait(15) and unpack None after the window is gone).
    state = {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "ready": False,
    }

    api = _JSApi(state)
    panel_url = "http://127.0.0.1:15502/index.html"

    # Wait for the local HTTP bridge to be ready before opening the WebView
    import time, urllib.request
    for _ in range(50):
        try:
            with urllib.request.urlopen(panel_url, timeout=0.3) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.1)

    print(f"[panel] loading {panel_url} ({width}x{height})")
    try:
        if x is not None and y is not None:
            x, y = _clamp_to_screen(x, y, width, height)
        else:
            # First launch: bottom-right of the primary monitor's work area.
            x, y = _default_position(width, height)
            if x is not None and y is not None:
                x, y = _clamp_to_screen(x, y, width, height)
        state["x"] = x
        state["y"] = y

        create_kwargs = {
            "width": width,
            "height": height,
            "frameless": True,
            "easy_drag": False,
            "background_color": "#0A0A0A",
            "js_api": api,
            "min_size": (_MIN_WIDTH, _MIN_HEIGHT),
        }
        if x is not None and y is not None:
            create_kwargs["x"] = x
            create_kwargs["y"] = y

        w = webview.create_window("Iris", panel_url, **create_kwargs)
        api._window = w

        def _on_moved(mx, my):
            if not state["ready"]:
                return
            try:
                state["x"] = int(mx)
                state["y"] = int(my)
            except (TypeError, ValueError):
                pass

        def _on_resized(rw, rh):
            # Ignore startup resize noise (was shrinking saved size each open).
            if not state["ready"]:
                return
            try:
                rw, rh = int(rw), int(rh)
                if _valid_size(rw, rh):
                    state["width"] = rw
                    state["height"] = rh
            except (TypeError, ValueError):
                pass

        def _on_shown():
            state["ready"] = True
            # Capture centred position after first show if none was saved.
            if state["x"] is None or state["y"] is None:
                try:
                    if w.gui is not None:
                        pos = w.gui.get_position(w.uid)
                        if pos:
                            state["x"], state["y"] = int(pos[0]), int(pos[1])
                except Exception:
                    pass

        def _on_closing():
            _save_geometry(state)

        w.events.moved += _on_moved
        w.events.resized += _on_resized
        w.events.shown += _on_shown
        w.events.closing += _on_closing
        webview.start(debug=False)

        # Fallback if closing event did not fire.
        _save_geometry(state)
    except Exception:
        print("[panel] failed to open")
        import traceback
        traceback.print_exc()
