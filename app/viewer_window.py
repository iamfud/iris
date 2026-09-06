"""Standalone Fullscreen Screenshot Annotation Viewer Window.

Opens the Iris Screenshot Viewer & Annotation Canvas in an independent fullscreen pywebview window.
"""

import logging
import multiprocessing
import os
import urllib.parse

log = logging.getLogger("iris.viewer_window")

_proc = None


class _ViewerApi:
    """Exposed to JavaScript as window.pywebview.api."""

    def __init__(self):
        self._window = None

    def close_viewer(self):
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass

    def close_panel(self):
        if self._window:
            try:
                self._window.destroy()
            except Exception:
                pass


def _clean_stale_caches(wv_dir: str):
    """Purge stale or corrupt shader caches and old crash dumps that cause black screen hangs."""
    try:
        import os
        import shutil
        eb = os.path.join(wv_dir, "EBWebView")
        if not os.path.isdir(eb):
            return
        for sub in ("GPUPersistentCache", "ShaderCache", "GrShaderCache", os.path.join("Default", "GPUCache")):
            target = os.path.join(eb, sub)
            if os.path.isdir(target):
                shutil.rmtree(target, ignore_errors=True)
        crash_dir = os.path.join(eb, "Crashpad", "reports")
        if os.path.isdir(crash_dir):
            for f in os.listdir(crash_dir):
                fp = os.path.join(crash_dir, f)
                if os.path.isfile(fp):
                    try:
                        os.remove(fp)
                    except Exception:
                        pass
    except Exception:
        pass


def _run_viewer(filename):
    try:
        from win_platform import init_dpi_awareness
        init_dpi_awareness()
    except Exception:
        pass

    try:
        import os
        import paths
        wv_data = paths.get_webview_data_dir("WebView2_Viewer")
        os.environ["WEBVIEW2_USER_DATA_FOLDER"] = wv_data
        _clean_stale_caches(wv_data)
        safe_args = "--disable-gpu-compositing --disable-direct-composition"
        existing = os.environ.get("WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS", "")
        if safe_args not in existing:
            os.environ["WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS"] = f"{existing} {safe_args}".strip()
    except Exception:
        pass

    try:
        import webview
    except ImportError:
        print("[viewer_window] pywebview not installed")
        return

    import time
    api = _ViewerApi()
    q = urllib.parse.urlencode({"view": "viewer", "file": filename, "_t": int(time.time())})
    url = f"http://127.0.0.1:15502/index.html?{q}"

    w = webview.create_window(
        "Iris Screenshot",
        url,
        fullscreen=True,
        frameless=True,
        easy_drag=False,
        background_color="#0A0A0A",
        js_api=api,
    )
    api._window = w

    def _on_closed():
        try:
            import ws_bridge
            ws_bridge.broadcast({"type": "library_update"})
        except Exception:
            pass

    w.events.closed += _on_closed
    webview.start(debug=False)

    try:
        import ws_bridge
        ws_bridge.broadcast({"type": "library_update"})
    except Exception:
        pass


def open_viewer(filename):
    """Open the standalone fullscreen screenshot annotation editor."""
    global _proc
    if _proc is not None and _proc.is_alive():
        try:
            _proc.terminate()
            _proc.join(timeout=0.5)
        except Exception:
            pass

    _proc = multiprocessing.Process(
        target=_run_viewer, args=(filename,), daemon=True, name="viewer_window"
    )
    _proc.start()
    log.info("[viewer_window] annotation editor started for %s (pid=%d)", filename, _proc.pid)


def is_viewer_open():
    """Return True if the screenshot annotation editor window is currently open."""
    global _proc
    return _proc is not None and _proc.is_alive()


def close_viewer():
    """Close the annotation editor if open."""
    global _proc
    if _proc is not None and _proc.is_alive():
        _proc.terminate()
        _proc.join(timeout=0.5)
    _proc = None
