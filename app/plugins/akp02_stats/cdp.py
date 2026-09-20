"""Minimal CDP client for headless browser rendering of AKP02 dashboard."""

import base64
import http.client
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any, Dict, Optional

from PIL import Image

log = logging.getLogger("iris.plugins.akp02_stats.cdp")

try:
    import websocket
except ImportError:
    websocket = None

W, H = 1920, 462

BROWSERS = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def find_browser() -> Optional[str]:
    for path in BROWSERS:
        if os.path.isfile(path):
            return path
    return None


class HeadlessRenderer:
    """Launches headless Chrome/Edge and communicates over DevTools Protocol."""

    def __init__(self, html_path: str, port: int = 9222):
        if websocket is None:
            raise RuntimeError("websocket-client is not installed (run: pip install websocket-client)")

        self.browser_exe = find_browser()
        if not self.browser_exe:
            raise FileNotFoundError("No supported browser (Microsoft Edge or Google Chrome) found.")

        self.html_path = html_path
        self.port = port
        self.profile_dir = tempfile.mkdtemp(prefix="iris-akp02-cdp-")
        self.proc: Optional[subprocess.Popen] = None
        self.ws: Optional[websocket.WebSocket] = None
        self._id = 0
        self.is_alive = False

        self._start()

    def _start(self):
        url = "file:///" + os.path.abspath(self.html_path).replace("\\", "/")
        try:
            with open(os.path.join(self.profile_dir, "First Run"), "w") as f:
                pass
        except Exception:
            pass

        args = [
            self.browser_exe,
            "--headless=new",
            "--no-sandbox",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-sync",
            "--enable-automation",
            "--disable-fre",
            "--disable-features=msEdgeSync,msEdgeFre,msImplicitSignin,msSignInFre,msEdgeWhatsNew,msWelcomePage,msFirstRun",
            "--disable-background-networking",
            "--disable-component-update",
            "--hide-scrollbars",
            "--disable-extensions",
            "--log-level=3",
            "--test-type",
            "--force-device-scale-factor=1",
            f"--window-size={W},{H}",
            f"--user-data-dir={self.profile_dir}",
            f"--remote-debugging-port={self.port}",
            "--remote-allow-origins=*",
            url,
        ]

        try:
            import psutil
            for p in psutil.process_iter(["pid", "name", "cmdline"]):
                try:
                    cmd = " ".join(p.info.get("cmdline") or [])
                    if f"--remote-debugging-port={self.port}" in cmd and p.pid != os.getpid():
                        p.kill()
                except Exception:
                    pass
        except Exception:
            pass

        self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.ws = self._connect(self.port)
        self.ws.settimeout(10)
        self.is_alive = True

        self.call("Emulation.setDeviceMetricsOverride", {
            "width": W,
            "height": H,
            "screenWidth": W,
            "screenHeight": H,
            "deviceScaleFactor": 1,
            "mobile": False,
        })
        time.sleep(0.5)

    def _connect(self, port: int, timeout: float = 15.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
                conn.request("GET", "/json/list")
                res = conn.getresponse()
                targets = json.loads(res.read().decode())
                conn.close()

                # Close any rogue sync dialog or internal browser pages
                for t in targets:
                    u = (t.get("url") or "").lower()
                    if u.startswith("edge://") or "sync-confirmation" in u:
                        try:
                            c_close = http.client.HTTPConnection("127.0.0.1", port, timeout=1)
                            c_close.request("GET", f"/json/close/{t['id']}")
                            c_close.getresponse().read()
                            c_close.close()
                        except Exception:
                            pass

                # Find valid dashboard page
                def _is_valid(t):
                    if t.get("type") != "page":
                        return False
                    u = (t.get("url") or "").lower()
                    if u.startswith("edge://") or u.startswith("chrome://") or "sync-confirmation" in u:
                        return False
                    return True

                page = next((t for t in targets if _is_valid(t)), None)
                if page and "webSocketDebuggerUrl" in page:
                    return websocket.create_connection(
                        page["webSocketDebuggerUrl"],
                        timeout=10,
                        suppress_origin=True
                    )
            except Exception:
                pass
            time.sleep(0.2)
        raise RuntimeError(f"Could not connect to browser DevTools on port {port}")

    def call(self, method: str, params: Optional[Dict[str, Any]] = None, timeout: float = 10.0) -> Dict[str, Any]:
        if not self.ws:
            raise RuntimeError("WebSocket connection is not open.")
        self._id += 1
        mid = self._id
        self.ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
        deadline = time.time() + timeout
        while True:
            try:
                raw = self.ws.recv()
                msg = json.loads(raw)
            except websocket.WebSocketTimeoutException:
                if time.time() > deadline:
                    raise TimeoutError(f"CDP call {method} timed out")
                continue
            if msg.get("id") == mid:
                if "error" in msg:
                    raise RuntimeError(msg["error"].get("message", str(msg["error"])))
                return msg.get("result") or {}

    def update(self, data: Dict[str, Any]):
        """Inject live telemetry into dashboard via window.__update(data)."""
        expr = f"window.__update({json.dumps(data)})"
        self.call("Runtime.evaluate", {"expression": expr, "returnByValue": False})

    def capture(self) -> Image.Image:
        """Screenshot the rendered page to a PIL RGB image."""
        res = self.call("Page.captureScreenshot", {
            "format": "png",
            "captureBeyondViewport": False,
            "fromSurface": True,
        })
        img_bytes = base64.b64decode(res["data"])
        return Image.open(io.BytesIO(img_bytes)).convert("RGB")

    def close(self):
        self.is_alive = False
        if self.ws:
            try:
                self.ws.close()
            except Exception:
                pass
            self.ws = None

        if self.proc:
            try:
                if sys.platform == "win32" and self.proc.pid:
                    subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=4)
                else:
                    self.proc.terminate()
                    self.proc.wait(timeout=2)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
            self.proc = None

        if self.profile_dir and os.path.isdir(self.profile_dir):
            try:
                shutil.rmtree(self.profile_dir, ignore_errors=True)
            except Exception:
                pass
