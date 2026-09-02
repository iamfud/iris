"""HTML settings panel — pywebview frameless wrapper.

Opens the settings HTML UI in a native window with no browser chrome.
Uses multiprocessing so pywebview gets its own main thread (required by Edge/WebView2 on Windows).
HTML and API both load from the local HTTP bridge (same-origin) so no CORS is needed.
"""

import ctypes
import json
import logging
import multiprocessing
import threading
import time

log = logging.getLogger("iris.panel")

_DEFAULT_WIDTH = 950
_DEFAULT_HEIGHT = 680
_MIN_WIDTH = 800
_MIN_HEIGHT = 560

_proc = None
_NAV_QUEUE = None


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
            try:
                self._window.hide()
            except Exception:
                pass

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

    def restore_default_size(self):
        """Restore the settings panel to its default 950x680 resolution."""
        if not self._window:
            return
        try:
            self._window.resize(_DEFAULT_WIDTH, _DEFAULT_HEIGHT)
            self._state["width"] = _DEFAULT_WIDTH
            self._state["height"] = _DEFAULT_HEIGHT
            _save_geometry(self._state)
        except Exception:
            pass

    def open_fullscreen_viewer(self, filename):
        """Open a standalone full-screen window for screenshot inspection & markup."""
        try:
            import webview
            import urllib.parse
            q = urllib.parse.urlencode({"view": "viewer", "file": filename})
            url = f"http://127.0.0.1:15502/index.html?{q}"
            vapi = _ViewerJSApi(None)
            vw = webview.create_window(
                "Iris Screenshot",
                url,
                fullscreen=True,
                frameless=True,
                easy_drag=False,
                background_color="#0A0A0A",
                js_api=vapi
            )
            vapi._window = vw
            return True
        except Exception as e:
            log.warning("[panel] open_fullscreen_viewer failed: %s", e)
            return False


class _ViewerJSApi:
    """Exposed to JavaScript in the standalone fullscreen viewer window."""

    def __init__(self, window):
        self._window = window

    def close_panel(self):
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass

    def close_viewer(self):
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass


def _find_windows_for_pid(pid: int) -> list:
    """Find top-level window handles owned by process pid."""
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

            # Exclude helper / hook / crashpad / message windows
            if any(ign in cname for ign in ("GDI+", ".NET", "MSCTFIME", "Default IME", "Message", "Chrome_WidgetWin")):
                return True

            tbuf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, tbuf, 256)
            title = tbuf.value or ""

            rect = ctypes.wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(rect))
            if (rect.right - rect.left > 80) and (rect.bottom - rect.top > 80):
                if title == "Iris":
                    hwnds.insert(0, hwnd)
                else:
                    hwnds.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    cb = WNDENUMPROC(enum_cb)
    try:
        user32.EnumWindows(cb, 0)
    except Exception as ex:
        log.warning("[panel] EnumWindows failed: %s", ex)

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


def is_panel_open():
    """Return True if the settings panel / library window process is running."""
    global _proc
    return _proc is not None and _proc.is_alive()


def open_panel(width=_DEFAULT_WIDTH, height=_DEFAULT_HEIGHT, query_params=None, page=None, tab=None, action=None, app_tag=None, viewer_file=None):
    """Open the settings panel. If already open, navigates to target page/tab/action and brings to foreground."""
    global _proc, _NAV_QUEUE

    nav_targets = None
    if page or tab or action or app_tag or viewer_file:
        if query_params is None:
            query_params = {}
        elif not isinstance(query_params, dict):
            query_params = {"q": str(query_params)}
        if page:
            query_params["page"] = str(page)
        if tab:
            query_params["tab"] = str(tab)
        if action:
            query_params["action"] = str(action)
        if app_tag:
            query_params["app"] = str(app_tag)
        if viewer_file:
            query_params["file"] = str(viewer_file)
        nav_targets = {
            "page": str(page or "library"),
            "tab": str(tab or "notes"),
            "action": action,
            "app": app_tag,
            "viewer_file": viewer_file,
        }

    if _NAV_QUEUE is None:
        _NAV_QUEUE = multiprocessing.Queue()

    if _proc is not None and _proc.is_alive():
        if nav_targets:
            try:
                # Deterministic IPC to the panel subprocess, independent of the
                # websocket broadcast (which can drop when the WS server restarts
                # or the webview has not connected yet).
                _NAV_QUEUE.put(nav_targets)
            except Exception:
                pass
            # Broadcast live navigation to all connected webviews
            try:
                import ws_bridge
                ws_bridge.broadcast({
                    "type": "navigate",
                    "page": page or "library",
                    "tab": tab or "notes",
                    "action": action,
                    "app": app_tag,
                    "viewer_file": viewer_file,
                })
            except Exception:
                pass

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
    except Exception:
        x = y = None

    w, h = _DEFAULT_WIDTH, _DEFAULT_HEIGHT
    if x is not None and y is not None:
        try:
            x, y = int(x), int(y)
        except (TypeError, ValueError):
            x = y = None

    _proc = multiprocessing.Process(
        target=_run, args=(w, h, x, y, query_params, _NAV_QUEUE), daemon=True, name="panel"
    )
    _proc.start()
    log.info("[panel] process started (pid=%d)", _proc.pid)



def close_panel():
    """Close the panel if open."""
    global _proc, _NAV_QUEUE
    if _proc is not None and _proc.is_alive():
        _proc.terminate()
        _proc.join(timeout=2)
    _proc = None
    _NAV_QUEUE = None


def toggle_panel():
    """Toggle the settings panel. If open and visible, close it; otherwise open it."""
    global _proc
    if _proc is not None and _proc.is_alive():
        hwnds = _find_windows_for_pid(_proc.pid)
        if hwnds:
            close_panel()
            log.info("[panel] toggled panel closed")
            return
        else:
            close_panel()
    open_panel()


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
        log.warning("[panel] failed to save window position: %s", e)


def _ensure_child_logger():
    """Ensure the child process has a working file logger (print goes nowhere with console=False)."""
    import os, sys
    from logging.handlers import RotatingFileHandler
    root = logging.getLogger()
    if any(isinstance(h, RotatingFileHandler) for h in root.handlers):
        return
    if getattr(sys, "frozen", False):
        log_dir = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Iris")
    else:
        log_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(log_dir, exist_ok=True)
    handler = RotatingFileHandler(
        os.path.join(log_dir, "iris.log"),
        maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-5s  [%(name)s]  %(message)s", datefmt="%H:%M:%S"))
    root.setLevel(logging.INFO)
    root.addHandler(handler)


def _build_nav_js(item):
    """Build a JS snippet that navigates the webview to the target page/tab and bookmarks the URL."""
    page = item.get("page")
    if not page:
        return None
    tab = item.get("tab")
    return "window.irisSetPage && window.irisSetPage(%s, %s);" % (
        json.dumps(str(page)),
        json.dumps(str(tab) if tab else ""),
    )


def _nav_loop(nav_queue, state, window):
    """Consume navigation directives from the parent process and apply them in the webview."""
    while True:
        try:
            item = nav_queue.get()
        except Exception:
            return
        if not isinstance(item, dict):
            continue
        try:
            js = _build_nav_js(item)
            if not js:
                continue
            deadline = time.time() + 30
            while not state.get("ready") and time.time() < deadline:
                time.sleep(0.1)
            if not state.get("ready"):
                continue
            window.evaluate_js(js)
        except Exception:
            pass


def _run(width, height, x=None, y=None, query_params=None, nav_queue=None):
    _ensure_child_logger()

    try:
        from win_platform import init_dpi_awareness
        init_dpi_awareness()
    except Exception:
        pass

    try:
        import os
        import paths
        wv_data = paths.get_webview_data_dir("WebView2_panel")
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = wv_data
        # Ensure standard hardware acceleration and DirectComposition
        if "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS" in os.environ:
            os.environ.pop("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", None)
    except Exception as exc:
        log.error("[panel] WebView2 data-folder setup failed: %s", exc)

    try:
        import webview
    except ImportError:
        log.error("[panel] pywebview not installed — pip install pywebview")
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
    import urllib.parse
    import urllib.request
    if query_params:
        if isinstance(query_params, dict):
            qs = urllib.parse.urlencode(query_params)
        else:
            qs = str(query_params).lstrip("?")
        panel_url = f"http://127.0.0.1:15502/index.html?{qs}"
    else:
        panel_url = "http://127.0.0.1:15502/index.html"

    # Pre-flight check: ensure local HTTP server is responding before launching webview
    for _ in range(25):
        try:
            with urllib.request.urlopen("http://127.0.0.1:15502/api/status", timeout=0.2) as resp:
                if resp.status == 200:
                    break
        except Exception:
            time.sleep(0.04)

    log.info("[panel] loading %s (%dx%d)", panel_url, width, height)
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
            # Ignore resize events so settings window geometry stays clean and fixed
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

        if nav_queue is not None:
            threading.Thread(
                target=_nav_loop,
                args=(nav_queue, state, api._window),
                daemon=True,
                name="panel-nav",
            ).start()

        webview.start(debug=False)

        # Fallback if closing event did not fire.
        _save_geometry(state)
    except Exception:
        log.error("[panel] failed to open", exc_info=True)
