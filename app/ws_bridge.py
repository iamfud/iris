"""WebSocket bridge — broadcasts notification data to Iris plugin.

Also runs an HTTP server to serve the settings HTML UI and plugin API.
"""

import asyncio
import json
import logging
import os
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from functools import partial

import websockets

log = logging.getLogger("iris.ws_bridge")

CLIENTS = set()
_loop = None
_app = None

_HTML_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "HTML")


def register_app(app):
    """Register the IrisApp instance so the HTTP API can access config/serial."""
    global _app
    _app = app


def _sync_next_alarm(serial_sender, alarms):
    """Push the next due alarm to the device (mirrors settings_dialog logic)."""
    import datetime
    enabled = [a for a in alarms if a.get("enabled") and a.get("days")]
    if not enabled:
        serial_sender.set_live("alarm_enabled", "0")
        serial_sender.queue_on_connect("alarm_enabled", "0")
        return

    now = datetime.datetime.now()

    def _secs(a):
        mask = a.get("days", 127)
        h, m = a["hour"], a["minute"]
        for off in range(8):
            d = now + datetime.timedelta(days=off)
            fw = (d.weekday() + 1) % 7
            if not (mask >> fw) & 1:
                continue
            t = d.replace(hour=h, minute=m, second=0, microsecond=0)
            if t > now:
                return (t - now).total_seconds()
        return float("inf")

    alarm = min(enabled, key=_secs)
    import time as _t
    for key, val in [
        ("alarm_hour", str(alarm["hour"])),
        ("alarm_minute", str(alarm["minute"])),
        ("alarm_days", str(alarm["days"])),
        ("alarm_enabled", "1"),
        ("alarm_clear_dismiss", "1"),
        ("alarm_message", alarm.get("message", "").replace("=", " ").replace("\n", " ")[:120]),
    ]:
        serial_sender.set_live(key, val)
        serial_sender.queue_on_connect(key, val)


# ── WebSocket ──────────────────────────────────────────────────

async def handler(websocket):
    CLIENTS.add(websocket)
    try:
        await websocket.wait_closed()
    finally:
        CLIENTS.remove(websocket)


async def _serve_ws(port):
    async with websockets.serve(handler, "localhost", port):
        log.info("WS bridge listening on port %d", port)
        await asyncio.Future()


# ── HTTP server (HTML + API) ───────────────────────────────────

class _RequestHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def do_GET(self):
        if self.path == "/api/plugins/state":
            self._send_json(_get_plugin_state())
        elif self.path == "/api/plugins/list":
            self._send_json(_get_plugin_list())
        elif self.path == "/api/plugins/config":
            self._send_json(_get_plugins_config())
        elif self.path.startswith("/api/plugins/") and self.path.endswith("/snapshot"):
            name = self.path.split("/")[3]
            self._send_json(_get_plugin_snapshot(name))
        elif self.path == "/api/config":
            self._send_json(_get_config())
        elif self.path == "/api/status":
            self._send_json(_get_device_status())
        elif self.path == "/api/settings/pages":
            self._send_json(_get_settings_pages())
        elif self.path == "/api/sounds":
            self._send_json(_get_sounds())
        elif self.path.startswith("/api/sounds/preview/"):
            self._handle_sound_preview(self.path.split("/")[-1])
        elif self.path == "/api/sounds/stop":
            self._handle_sound_stop()
        elif self.path.startswith("/media/"):
            self._serve_media(self.path[7:])
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/api/config":
            self._handle_save_config()
        elif self.path.startswith("/api/plugins/config/"):
            self._handle_save_plugin_config(self.path.split("/")[-1])
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def _serve_media(self, filename):
        import mimetypes
        safe = os.path.basename(filename)
        _media_dir = os.path.join(
            os.path.dirname(os.path.abspath(__file__)), os.pardir, "media")
        fpath = os.path.join(_media_dir, safe)
        if not os.path.isfile(fpath):
            self.send_error(404)
            return
        mime = mimetypes.guess_type(safe)[0] or "application/octet-stream"
        try:
            with open(fpath, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", mime)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500)

    def _handle_sound_preview(self, name):
        import alarm_sound
        ok = alarm_sound.play(name)
        self._send_json({"ok": ok})

    def _handle_sound_stop(self):
        import alarm_sound
        alarm_sound.stop()
        self._send_json({"ok": True})

    def _send_json(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _handle_save_config(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            if _app is None:
                self.send_error(503, "App not registered")
                return
            from config import save_config
            _app.cfg.update(body)
            save_config(_app.cfg)
            self._push_config_to_device(body)
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("[http] save config failed: %s", e)
            self.send_error(500, str(e))

    def _push_config_to_device(self, body):
        try:
            from serial_comm import serial_sender
        except Exception:
            return
        if not serial_sender.connected_port():
            return
        import time as _t
        import threading

        def _send():
            try:
                from settings_dialog import FEATURE_KEYS
                for key_pair in FEATURE_KEYS:
                    key = key_pair[0] if isinstance(key_pair, (list, tuple)) else key_pair
                    if key in body:
                        val = "1" if body[key] else "0"
                        serial_sender.set_live(key, val)
                        _t.sleep(0.02)

                if "feature_large_clock" in body or "feature_day_clock" in body or "feature_time" in body:
                    mode = "Small Clock"
                    if body.get("feature_large_clock", _app.cfg.get("feature_large_clock")):
                        mode = "Large Clock"
                    elif body.get("feature_day_clock", _app.cfg.get("feature_day_clock")):
                        mode = "Day Clock"
                    serial_sender.set_live("feature_large_clock", "1" if mode == "Large Clock" else "0")
                    _t.sleep(0.02)
                    serial_sender.set_live("feature_day_clock", "1" if mode == "Day Clock" else "0")
                    _t.sleep(0.02)
                    mb = "1" if _app.cfg.get("feature_minute_bar", True) and mode != "Large Clock" else "0"
                    serial_sender.set_live("feature_minute_bar", mb)
                    _t.sleep(0.02)

                if "user_name" in body:
                    raw = body["user_name"].strip() if isinstance(body["user_name"], str) else ""
                    serial_sender.set_live("user_name", raw)
                    serial_sender.queue_on_connect("user_name", raw)

                if "alarms" in body:
                    _sync_next_alarm(serial_sender, body.get("alarms", []))
            except Exception as e:
                log.warning("[http] device push failed: %s", e)

        threading.Thread(target=_send, daemon=True).start()

    def _handle_save_plugin_config(self, name):
        try:
            import plugin_manager
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            plugin_manager.set_plugin_config(name, body)
            # Trigger immediate check so exe change takes effect
            plugin_manager.check_plugins()
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("[http] save plugin config failed: %s", e)
            self.send_error(500, str(e))

    def log_message(self, fmt, *args):
        # suppress per-request logs
        pass


def _get_plugin_state():
    import plugin_manager
    result = {}
    for name, inst in plugin_manager._instances.items():
        try:
            if hasattr(inst, "poll"):
                result[name] = inst.poll()
            else:
                result[name] = {"available": False}
        except Exception:
            result[name] = {"available": False}
    return result


def _get_plugin_snapshot(name):
    import plugin_manager
    inst = plugin_manager.get(name)
    if inst and hasattr(inst, "snapshot"):
        try:
            return inst.snapshot()
        except Exception:
            pass
    import importlib
    try:
        mod = importlib.import_module(f"plugins.{name}.connector")
        if hasattr(mod, "read_journal_snapshot"):
            return mod.read_journal_snapshot()
    except Exception:
        pass
    return {"available": False, "state": {}, "status": {}}


def _get_plugins_config():
    import plugin_manager
    result = {}
    for name, manifest in plugin_manager.discover_plugins():
        pcfg = plugin_manager.get_plugin_config(name)
        status = plugin_manager.get_plugin_status(name)
        result[name] = {
            "display_name": manifest.get("display_name", name),
            "description": manifest.get("description", ""),
            "icon": manifest.get("icon", "extension"),
            "type": manifest.get("type", "service"),
            "exe_path": pcfg.get("exe_path", ""),
            "exe_default": manifest.get("exe_default", ""),
            "enabled": pcfg.get("enabled", True),
            "running": plugin_manager.is_running(name),
            "status_code": status["status_code"],
            "status_label": status["status_label"],
            "message": status["message"],
            "requirements": status.get("requirements", []),
            "settings": manifest.get("settings", []),
        }
    return result


def _get_plugin_list():
    import plugin_manager
    return [
        {"name": name, "display_name": manifest.get("display_name", name)}
        for name, manifest in plugin_manager.discover_plugins()
    ]


def _get_sounds():
    import alarm_sound
    media_dir = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), os.pardir, "media")
    sounds = []
    for name in alarm_sound.list_sounds():
        path = alarm_sound.SOUNDS.get(name, "")
        sounds.append({
            "name": name,
            "file": os.path.basename(path),
            "exists": os.path.isfile(path),
        })
    return {"sounds": sounds, "media_url": "/media"}


def _get_settings_pages():
    pages_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "settings_pages.json")
    try:
        with open(pages_path) as f:
            return json.load(f)
    except Exception:
        return {"pages": []}


def _get_config():
    if _app is None:
        return {}
    return {k: v for k, v in _app.cfg.items() if not k.startswith("_")}


def _get_device_status():
    from serial_comm import serial_sender
    port = serial_sender.connected_port()
    connected = port is not None
    last_notif = ""
    if _app is not None:
        for p in _app._providers:
            if hasattr(p, "poll"):
                data = p.poll()
                if "last_notif" in data:
                    last_notif = data["last_notif"]
    return {
        "connected": connected,
        "port": port or "",
        "last_notification": last_notif,
    }


def start_http(port=15502):
    os.makedirs(_HTML_DIR, exist_ok=True)
    handler = partial(_RequestHandler, directory=_HTML_DIR)
    server = HTTPServer(("0.0.0.0", port), handler)
    log.info("HTTP server listening on port %d (serving %s)", port, _HTML_DIR)
    server.serve_forever()


# ── Public API ─────────────────────────────────────────────────

def start(ws_port=15501, http_port=15502):
    global _loop
    _loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_loop)

    # start HTTP server in a background thread
    threading.Thread(target=start_http, args=(http_port,), daemon=True, name="http-server").start()

    # run WS server on main asyncio loop
    _loop.run_until_complete(_serve_ws(ws_port))


def broadcast(data):
    if _loop is None or not CLIENTS:
        return
    msg = json.dumps(data)

    async def _send_all():
        await asyncio.gather(
            *(c.send(msg) for c in set(CLIENTS)),
            return_exceptions=True,
        )

    asyncio.run_coroutine_threadsafe(_send_all(), _loop)
