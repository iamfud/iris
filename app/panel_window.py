"""HTML settings panel — pywebview frameless wrapper.

Opens the settings HTML UI in a native window with no browser chrome.
Uses multiprocessing so pywebview gets its own main thread (required by Edge/WebView2 on Windows).
HTML loads from file:// for instant render; API data comes from HTTP (ws_bridge).
"""

import ctypes
import logging
import multiprocessing
import os

log = logging.getLogger("iris.panel")

_html_dir = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "HTML"
)

_proc = None


class _JSApi:
    """Exposed to JavaScript as window.pywebview.api."""

    def __init__(self):
        self._window = None

    def move_window(self, dx, dy):
        if self._window:
            self._x = self._window.x + dx
            self._y = self._window.y + dy
            self._window.move(self._x, self._y)

    def close_panel(self):
        if self._window:
            self._window.destroy()

    def browse_exe(self):
        if not self._window:
            return ""
        try:
            import webview
            result = self._window.create_file_dialog(
                webview.OPEN_DIALOG,
                file_types=("Executable (*.exe)",),
            )
            return result[0] if result else ""
        except Exception:
            return ""


def open_panel(width=950, height=680):
    """Open the settings panel. Reuses existing process if still alive."""
    global _proc

    if _proc is not None and _proc.is_alive():
        log.info("[panel] already open, bringing to front")
        return

    try:
        from config import load_config
        cfg = load_config()
        x = cfg.get("panel_window_x")
        y = cfg.get("panel_window_y")
        w = cfg.get("panel_window_width", width)
        h = cfg.get("panel_window_height", height)
    except Exception:
        x = y = None
        w, h = width, height

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


def _clamp_to_screen(x, y, width, height):
    """Keep the window at least 100x100 pixels on screen."""
    try:
        sx, sy, sw, sh = _virtual_screen_bounds()
        # Ensure a reasonable portion of the window stays visible.
        x = max(sx - width + 100, min(x, sx + sw - 100))
        y = max(sy, min(y, sy + sh - 100))
        return x, y
    except Exception:
        return x, y


def _run(width, height, x=None, y=None):
    try:
        import webview
    except ImportError:
        print("[panel] pywebview not installed — pip install pywebview")
        return

    api = _JSApi()
    html_path = os.path.join(_html_dir, "index.html")
    file_url = "file:///" + html_path.replace("\\", "/")
    print(f"[panel] loading {file_url} ({width}x{height})")
    try:
        if x is not None and y is not None:
            x, y = _clamp_to_screen(x, y, width, height)

        w = webview.create_window(
            "Iris",
            file_url,
            width=width,
            height=height,
            x=x,
            y=y,
            frameless=True,
            easy_drag=False,
            background_color="#0A0A0A",
            js_api=api,
            min_size=(600, 400),
        )
        api._window = w

        def _save_position():
            try:
                x_save = w.x
                y_save = w.y
                w_save = w.width
                h_save = w.height
                if x_save is None or y_save is None:
                    return
                if x_save < -10000 or y_save < -10000:
                    return
                from config import load_config, save_config
                cfg = load_config()
                cfg["panel_window_x"] = x_save
                cfg["panel_window_y"] = y_save
                cfg["panel_window_width"] = w_save
                cfg["panel_window_height"] = h_save
                save_config(cfg)
            except Exception as e:
                print("[panel] failed to save window position:", e)

        w.events.closed += _save_position
        webview.start(debug=False)

        # Fallback in case the closed event didn't fire.
        _save_position()
    except Exception:
        print("[panel] failed to open")
        import traceback
        traceback.print_exc()
