"""HTML settings panel — pywebview frameless wrapper.

Opens the settings HTML UI in a native window with no browser chrome.
Uses multiprocessing so pywebview gets its own main thread (required by Edge/WebView2 on Windows).
HTML loads from file:// for instant render; API data comes from HTTP (ws_bridge).
"""

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

    _proc = multiprocessing.Process(
        target=_run, args=(width, height), daemon=True, name="panel"
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


def _run(width, height):
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
        w = webview.create_window(
            "Iris",
            file_url,
            width=width,
            height=height,
            frameless=True,
            easy_drag=False,
            background_color="#0A0A0A",
            js_api=api,
            min_size=(600, 400),
        )
        api._window = w
        webview.start(debug=False)
    except Exception:
        print("[panel] failed to open")
        import traceback
        traceback.print_exc()
