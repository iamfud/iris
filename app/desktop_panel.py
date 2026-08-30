"""Desktop HTML Companion Panel — borderless pywebview wrapper.

Loads the existing Iris web portal directly (http://127.0.0.1:15502/index.html?view=panel)
in a dedicated frameless native window on the desktop.
Toggled via the global hotkey Ctrl + Shift + I.
"""

import ctypes
import logging
import multiprocessing
import os
import sys
import time

log = logging.getLogger("iris.desktop_panel")

_DEFAULT_WIDTH = 284
_DEFAULT_HEIGHT = 585
_MIN_WIDTH = 240
_MIN_HEIGHT = 400

_proc = None


class _DesktopPanelJSApi:
    """Exposed to JavaScript as window.pywebview.api."""

    def __init__(self, state):
        self._window = None
        self._hwnd = None
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

    def set_pinned(self, is_pinned):
        try:
            self._state["pinned"] = bool(is_pinned)
            _save_geometry(self._state)
            hwnd = self._hwnd
            if not hwnd:
                hwnds = _find_windows_for_pid(os.getpid())
                if hwnds:
                    hwnd = hwnds[0]
                    self._hwnd = hwnd
            if hwnd:
                user32 = ctypes.windll.user32
                HWND_TOPMOST = -1
                HWND_NOTOPMOST = -2
                SWP_NOMOVE = 0x0002
                SWP_NOSIZE = 0x0001
                SWP_NOACTIVATE = 0x0010
                h_insert = HWND_TOPMOST if is_pinned else HWND_NOTOPMOST
                user32.SetWindowPos(hwnd, h_insert, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE)
        except Exception as e:
            log.warning("[desktop_panel] set_pinned failed: %s", e)

    def is_pinned(self):
        return bool(self._state.get("pinned", False))

    def hide_on_blur(self):
        if not self._state.get("pinned", False):
            if self._window:
                try:
                    self._window.hide()
                except Exception:
                    pass

    def resize_to_content(self, target_h):
        if not self._window:
            return
        try:
            target_h = int(target_h)
            if target_h < _MIN_HEIGHT:
                target_h = _MIN_HEIGHT
            cur_h = self._state.get("height", _DEFAULT_HEIGHT)
            if abs(cur_h - target_h) < 4:
                return

            user32 = ctypes.windll.user32
            sh = user32.GetSystemMetrics(1)  # SM_CYSCREEN
            w = self._state.get("width", _DEFAULT_WIDTH)
            x = self._state.get("x")
            y = self._state.get("y")

            if y is not None and x is not None and (y + cur_h >= sh - 120):
                new_y = max(20, y + (cur_h - target_h))
                self._window.resize(w, target_h)
                self._window.move(x, new_y)
                self._state["y"] = new_y
            else:
                self._window.resize(w, target_h)

            self._state["height"] = target_h
            _save_geometry(self._state)
        except Exception as e:
            log.warning("[desktop_panel] resize_to_content failed: %s", e)


def _find_windows_for_pid(pid: int) -> list:
    """Find the actual pywebview top-level window handle owned by process pid."""
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

            # Exclude helper / hook / message windows
            if "GDI+" in cname or ".NET" in cname or "MSCTFIME" in cname or "Default IME" in cname or "Message" in cname:
                return True

            tbuf = ctypes.create_unicode_buffer(256)
            user32.GetWindowTextW(hwnd, tbuf, 256)
            title = tbuf.value or ""

            if title == "Iris Companion":
                hwnds.insert(0, hwnd)
            elif not title:
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

        try:
            from config import load_config
            pinned = load_config().get("desktop_panel_pinned", False)
        except Exception:
            pinned = False

        if user32.IsIconic(hwnd):
            user32.ShowWindow(hwnd, SW_RESTORE)
        else:
            user32.ShowWindow(hwnd, SW_SHOW)

        h_insert = HWND_TOPMOST if pinned else HWND_NOTOPMOST
        user32.SetWindowPos(hwnd, h_insert, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

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

        try:
            user32.SwitchToThisWindow(hwnd, True)
        except Exception:
            pass
    except Exception as ex:
        log.warning("[desktop_panel] _bring_to_foreground failed: %s", ex)


def _hide_window(hwnd):
    """Hide the window handle."""
    if not hwnd:
        return
    try:
        user32 = ctypes.windll.user32
        SW_HIDE = 0
        user32.ShowWindow(hwnd, SW_HIDE)
    except Exception:
        pass


def toggle_desktop_panel():
    """Toggle visibility of the desktop HTML companion panel."""
    global _proc
    user32 = ctypes.windll.user32

    if _proc is not None and _proc.is_alive():
        hwnds = _find_windows_for_pid(_proc.pid)
        if hwnds:
            target_hwnd = hwnds[0]
            if user32.IsWindowVisible(target_hwnd):
                fg = user32.GetForegroundWindow()
                if fg == target_hwnd or fg in hwnds:
                    _hide_window(target_hwnd)
                    log.info("[desktop_panel] hidden on toggle")
                    return
                else:
                    _bring_to_foreground(target_hwnd)
                    log.info("[desktop_panel] brought to foreground on toggle")
                    return
            else:
                _bring_to_foreground(target_hwnd)
                log.info("[desktop_panel] shown on toggle")
                return

    # Process not running -> open it
    open_desktop_panel()


def open_desktop_panel():
    """Open the desktop HTML companion panel."""
    global _proc

    if _proc is not None and _proc.is_alive():
        hwnds = _find_windows_for_pid(_proc.pid)
        if hwnds:
            for hwnd in hwnds:
                _bring_to_foreground(hwnd)
            log.info("[desktop_panel] brought existing window to foreground (pid=%d)", _proc.pid)
            return
        else:
            close_desktop_panel()

    try:
        from config import load_config
        cfg = load_config()
        w = cfg.get("desktop_panel_w", _DEFAULT_WIDTH)
        h = cfg.get("desktop_panel_h", _DEFAULT_HEIGHT)
        x = cfg.get("desktop_panel_x")
        y = cfg.get("desktop_panel_y")
        pinned = cfg.get("desktop_panel_pinned", False)
    except Exception:
        w, h, x, y, pinned = _DEFAULT_WIDTH, _DEFAULT_HEIGHT, None, None, False

    _proc = multiprocessing.Process(
        target=_run, args=(w, h, x, y, pinned), daemon=True, name="desktop_panel"
    )
    _proc.start()
    log.info("[desktop_panel] process started (pid=%d)", _proc.pid)


def close_desktop_panel():
    """Close and terminate the desktop panel process."""
    global _proc
    if _proc is not None and _proc.is_alive():
        _proc.terminate()
        _proc.join(timeout=1.5)
    _proc = None


def _default_position(width, height):
    """Position on the bottom-right of the primary screen with margin."""
    try:
        user32 = ctypes.windll.user32
        sw = user32.GetSystemMetrics(0)  # SM_CXSCREEN
        sh = user32.GetSystemMetrics(1)  # SM_CYSCREEN
        margin = 24
        x = sw - width - margin
        y = sh - height - margin - 48  # above taskbar
        return max(0, x), max(0, y)
    except Exception:
        return 100, 100


def _save_geometry(state):
    try:
        from config import load_config, save_config
        cfg = load_config()
        changed = False
        if state.get("x") is not None and cfg.get("desktop_panel_x") != state["x"]:
            cfg["desktop_panel_x"] = state["x"]
            changed = True
        if state.get("y") is not None and cfg.get("desktop_panel_y") != state["y"]:
            cfg["desktop_panel_y"] = state["y"]
            changed = True
        if state.get("width") is not None and cfg.get("desktop_panel_w") != state["width"]:
            cfg["desktop_panel_w"] = state["width"]
            changed = True
        if state.get("height") is not None and cfg.get("desktop_panel_h") != state["height"]:
            cfg["desktop_panel_h"] = state["height"]
            changed = True
        if state.get("pinned") is not None and cfg.get("desktop_panel_pinned") != state["pinned"]:
            cfg["desktop_panel_pinned"] = state["pinned"]
            changed = True
        if changed:
            save_config(cfg)
    except Exception as e:
        log.warning("[desktop_panel] failed to save geometry: %s", e)


def _run(width, height, x=None, y=None, pinned=False):
    """Entry point for the pywebview desktop companion process."""
    try:
        import paths
        wv_data = paths.get_webview_data_dir("WebView2_Companion")
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = wv_data
    except Exception:
        pass

    try:
        import webview
    except ImportError:
        print("[desktop_panel] pywebview not installed")
        return

    state = {
        "x": x,
        "y": y,
        "width": width,
        "height": height,
        "pinned": bool(pinned),
        "ready": False,
    }
    api = _DesktopPanelJSApi(state)
    panel_url = f"http://127.0.0.1:15502/index.html?view=panel&mode=desktop&_t={int(time.time())}"

    if x is None or y is None:
        x, y = _default_position(width, height)
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

    try:
        w = webview.create_window("Iris Companion", panel_url, **create_kwargs)
        api._window = w

        def _on_moved(mx, my):
            if not state["ready"]:
                return
            try:
                state["x"] = int(mx)
                state["y"] = int(my)
            except Exception:
                pass

        def _on_shown():
            state["ready"] = True
            hwnds = _find_windows_for_pid(os.getpid())
            if hwnds:
                api._hwnd = hwnds[0]
                if state.get("pinned", False):
                    api.set_pinned(True)
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
        w.events.shown += _on_shown
        w.events.closing += _on_closing
        webview.start(debug=False)
        _save_geometry(state)
    except Exception as e:
        print(f"[desktop_panel] error: {e}")
