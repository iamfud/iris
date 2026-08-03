"""WebSocket bridge — broadcasts notification data to Iris plugin.

Also runs an HTTP server to serve the settings HTML UI and plugin API.
"""

import asyncio
import json
import logging
import os
import secrets
import socket
import threading
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial

import websockets

import win_volume

log = logging.getLogger("iris.ws_bridge")

CLIENTS = set()
_loop = None
_app = None

# Per-process auth token. Generated once at import (fresh each launch) and
# required on every /api/* request. Injected into the served panel HTML so
# the same-origin page can read it without any cross-process secret passing.
_HTTP_TOKEN = secrets.token_urlsafe(32)

_HTML_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "HTML")


def register_app(app):
    """Register the IrisApp instance so the HTTP API can access config/serial."""
    global _app
    _app = app


def _sync_next_alarm(serial_sender, alarms):
    """Push the next due alarm to the device."""
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


def _ws_process_request(connection, request):
    """Reject WS connections without the correct token at the HTTP handshake."""
    try:
        path = getattr(request, "path", "") or ""
    except Exception:
        path = ""
    query = path.split("?", 1)[1] if "?" in path else ""
    token = ""
    for part in query.split("&"):
        if part.startswith("token="):
            token = part[len("token="):]
    if token == _HTTP_TOKEN:
        return None
    from websockets.datastructures import Headers
    from websockets.http11 import Response
    return Response(401, "Unauthorized", Headers(), b"unauthorized")


async def _serve_ws(port):
    host = _bind_host()
    async with websockets.serve(
            handler, host, port, process_request=_ws_process_request):
        log.info("WS bridge listening on %s:%d", host, port)
        await asyncio.Future()


# ── HTTP server (HTML + API) ───────────────────────────────────

def _bind_host():
    """Return the bind host for HTTP/WS: loopback unless LAN access is on."""
    try:
        if _app is not None and _app.cfg.get("lan_access"):
            return "0.0.0.0"
    except Exception:
        pass
    return "127.0.0.1"


def _is_loopback_mode():
    return _bind_host() == "127.0.0.1"


def _lan_ip():
    """Best-effort primary LAN IPv4 address (route to default gateway).

    Falls back to the machine hostname resolution if the UDP trick fails.
    """
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
        finally:
            s.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    try:
        return socket.gethostbyname(socket.gethostname())
    except Exception:
        return "127.0.0.1"


def _lan_url():
    """Panel URL a LAN device can open (token is injected server-side)."""
    host = _lan_ip()
    if _is_loopback_mode():
        host = "127.0.0.1"
    return "http://%s:15502/index.html" % host


def _qr_bytes():
    """Render the LAN panel URL as a QR code PNG."""
    import io
    try:
        import qrcode
    except ImportError:
        return None
    try:
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(_lan_url())
        qr.make(fit=True)
        img = qr.make_image(fill_color="#0f1014", back_color="#ffffff")
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except Exception:
        return None


class _RequestHandler(SimpleHTTPRequestHandler):

    def __init__(self, *args, directory=None, **kwargs):
        super().__init__(*args, directory=directory, **kwargs)

    def _authorized(self):
        """True when the request carries the correct auth token."""
        provided = self.headers.get("X-Iris-Token", "")
        return provided == _HTTP_TOKEN

    def _host_ok(self):
        """Block DNS-rebinding in loopback mode: Host must be a loopback name."""
        if not _is_loopback_mode():
            return True
        host = (self.headers.get("Host", "") or "").strip().lower()
        name = host.split(":", 1)[0]
        return name in ("127.0.0.1", "localhost", "[::1]")

    def _reject_unauthorized(self):
        self.send_response(401)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b'{"ok":false}')))
        self.end_headers()
        self.wfile.write(b'{"ok":false}')

    def do_GET(self):
        if self.path.startswith("/api/"):
            if not self._host_ok() or not self._authorized():
                self._reject_unauthorized()
                return
        if self.path == "/api/plugins/state":
            self._send_json(_get_plugin_state())
        elif self.path == "/api/plugins/list":
            self._send_json(_get_plugin_list())
        elif self.path == "/api/plugins/config":
            self._send_json(_get_plugins_config())
        elif self.path.startswith("/api/plugins/") and self.path.endswith("/snapshot"):
            name = self.path.split("/")[3]
            self._send_json(_get_plugin_snapshot(name))
        elif self.path.startswith("/api/plugins/") and self.path.endswith("/outputs"):
            name = self.path.split("/")[3]
            self._send_json(_get_plugin_outputs(name))
        elif self.path == "/api/config":
            self._send_json(_get_config())
        elif self.path == "/api/status":
            self._send_json(_get_device_status())
        elif self.path == "/api/settings/pages":
            self._send_json(_get_settings_pages())
        elif self.path == "/api/network/qr":
            self._serve_network_qr()
        elif self.path == "/api/sounds":
            self._send_json(_get_sounds())
        elif self.path.startswith("/api/sounds/preview/"):
            self._handle_sound_preview(self.path.split("/")[-1])
        elif self.path == "/api/sounds/stop":
            self._handle_sound_stop()
        elif self.path == "/api/vision/sensors":
            self._send_json(_get_vision_sensors())
        elif self.path == "/api/volume":
            self._send_json(_get_volume())
        elif self.path.startswith("/media/"):
            self._serve_media(self.path[7:])
        elif self.path in ("/", "/index.html"):
            self._serve_index()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith("/api/"):
            if not self._host_ok() or not self._authorized():
                self._reject_unauthorized()
                return
        if self.path == "/api/config":
            self._handle_save_config()
        elif self.path.startswith("/api/plugins/config/"):
            self._handle_save_plugin_config(self.path.split("/")[-1])
        elif self.path.startswith("/api/plugins/") and "/outputs" in self.path:
            name = self.path.split("/")[3]
            self._handle_save_plugin_outputs(name)
        elif self.path.startswith("/api/plugins/") and "/action/" in self.path:
            parts = self.path.split("/")
            name = parts[3]
            action_id = parts[5]
            self._handle_plugin_action(name, action_id)
        elif self.path == "/api/vision/sensors":
            self._handle_vision_create_sensor()
        elif self.path == "/api/vision/capture":
            self._handle_vision_capture()
        elif self.path == "/api/vision/test":
            self._handle_vision_test()
        elif self.path.startswith("/api/vision/sensors/") and self.path.endswith("/delete"):
            sensor_id = self.path.split("/")[-2]
            self._handle_vision_delete_sensor(sensor_id)
        elif self.path.startswith("/api/vision/sensors/"):
            sensor_id = self.path.split("/")[-1]
            self._handle_vision_update_sensor(sensor_id)
        elif self.path == "/api/volume":
            self._handle_volume_set()
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
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
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500)

    def _serve_network_qr(self):
        """Serve the LAN panel URL as a QR PNG (auth required via /api/)."""
        data = _qr_bytes()
        if data is None:
            self.send_error(500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/png")
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    def _serve_index(self):
        """Serve index.html with the auth token injected (same-origin panel)."""
        index_path = os.path.join(self.directory, "index.html")
        if not os.path.isfile(index_path):
            self.send_error(404)
            return
        try:
            with open(index_path, "rb") as f:
                html = f.read()
        except Exception:
            self.send_error(500)
            return
        meta = f'<meta name="iris-token" content="{_HTTP_TOKEN}">'
        if b"<head" in html[:2000]:
            html = html.replace(b"<head", meta.encode() + b"<head", 1)
        else:
            html = meta.encode() + html
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

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
            body = {k: v for k, v in body.items()
                    if k not in ("http_token", "lan_url")}
            _app.cfg.update(body)
            save_config(_app.cfg)
            self._push_config_to_device(body)
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("[http] save config failed: %s", e)
            self.send_error(500, str(e))

    _FEATURE_KEYS = [
        ("feature_time", "Time display"),
        ("feature_date", "Date (alternates with time)"),
        ("feature_minute_bar", "Minute bar"),
        ("feature_eyes", "Animated eyes"),
        ("feature_notifications", "Notifications"),
        ("feature_greeting", "Greeting message"),
        ("night_mode_enabled", "Night mode"),
        ("temp_alert", "Temp alert"),
        ("pc_stats_enabled", "PC Stats"),
    ]

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
                for key_pair in self._FEATURE_KEYS:
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
            if name == "vision":
                body = _merge_vision_config(body)
            plugin_manager.set_plugin_config(name, body)
            # Trigger immediate check so exe change takes effect
            plugin_manager.check_plugins()
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("[http] save plugin config failed: %s", e)
            self.send_error(500, str(e))

    def _handle_save_plugin_outputs(self, name):
        try:
            import plugin_manager
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            plugin_manager.set_plugin_outputs(name, body)
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("[http] save plugin outputs failed: %s", e)
            self.send_error(500, str(e))

    def _handle_plugin_action(self, name, action_id):
        try:
            import plugin_manager
            ok = plugin_manager.invoke_action(name, action_id)
            self._send_json({"ok": ok})
        except Exception as e:
            log.warning("[http] plugin action failed: %s", e)
            self.send_error(500, str(e))

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        return json.loads(self.rfile.read(length)) if length else {}

    def _handle_vision_capture(self):
        import vision
        root = _app._root if _app is not None else None
        rect = vision.select_region(root, timeout=90)
        if not rect:
            self._send_json({"cancelled": True})
            return
        x, y, w, h = rect
        bbox = (x, y, x + w, y + h)
        try:
            img_b64 = vision.screenshot_b64(bbox)
        except Exception as e:
            log.warning("[vision] capture failed: %s", e)
            self.send_error(500, str(e))
            return
        cx, cy = x + w // 2, y + h // 2
        exe = vision.resolve_exe_for_point(cx, cy)
        anchor = vision.monitor_containing(cx, cy)
        region = vision.region_to_pct(anchor, (x, y, w, h))
        self._send_json({
            "exe": exe,
            "anchor": anchor,
            "region": region,
            "screenshot_b64": img_b64,
        })

    def _handle_vision_test(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        import vision
        result = vision.measure(body)
        self._send_json({
            "value": result["value"],
            "active": result["active"],
            "mode": result["mode"],
        })

    def _handle_vision_create_sensor(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        if _app is None:
            self.send_error(503, "App not registered")
            return
        sensor = _normalize_sensor(body, _vision_sensors())
        _vision_sensors().append(sensor)
        _save_vision_config()
        self._send_json({"ok": True, "sensor": sensor})

    def _handle_vision_update_sensor(self, sensor_id):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        sensors = _vision_sensors()
        idx = next((i for i, s in enumerate(sensors) if s.get("id") == sensor_id), None)
        if idx is None:
            self.send_error(404, "sensor not found")
            return
        sensor = _normalize_sensor(body)
        sensor["id"] = sensor_id
        sensor["created"] = sensors[idx].get("created", 0)
        sensors[idx] = sensor
        _save_vision_config()
        self._send_json({"ok": True, "sensor": sensor})

    def _handle_vision_delete_sensor(self, sensor_id):
        sensors = _vision_sensors()
        before = len(sensors)
        _vision_sensors()[:] = [s for s in sensors if s.get("id") != sensor_id]
        _save_vision_config()
        self._send_json({"ok": len(_vision_sensors()) < before})

    def _handle_volume_set(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        try:
            value = int(body.get("volume"))
        except (TypeError, ValueError):
            self.send_error(400, "volume must be an integer")
            return
        import win_volume
        ok = win_volume.set_active_app_volume(max(0, min(100, value)))
        self._send_json({"ok": ok})

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
        capabilities = manifest.get("capabilities", {})
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
            "config": dict(pcfg),
            "capabilities": capabilities,
            "status_fields": manifest.get("status", []),
            "outputs_def": manifest.get("outputs", []),
            "outputs": plugin_manager.get_plugin_outputs(name),
            "live_data_def": manifest.get("live_data", {}),
            "actions_def": manifest.get("actions", []),
            "diagnostics_def": manifest.get("diagnostics", []),
            "labels": manifest.get("labels", {}),
            "log_path": pcfg.get("log_path", ""),
        }
    return result


def _get_plugin_outputs(name):
    import plugin_manager
    return plugin_manager.get_plugin_outputs(name)


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
    cfg = {k: v for k, v in _app.cfg.items()
           if not k.startswith("_") and k not in ("ha_token",)}
    cfg["http_token"] = _HTTP_TOKEN
    cfg["lan_url"] = _lan_url()
    return cfg


_HW_UNKNOWN = object()
_cached_hw_id = None


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
    hw_id = None
    if connected:
        hw_id = _detect_hardware()
    else:
        _clear_hw_cache()
    return {
        "connected": connected,
        "port": port or "",
        "device_id": hw_id,
        "device_name": DEVICE_TITLES.get(hw_id) if hw_id else None,
        "last_notification": last_notif,
    }


DEVICE_TITLES = {
    "d1mini_max7219_4": "Pixel Clock",
    "d1mini_max7219_8": "Pixel Clock XL",
}


def _detect_hardware():
    global _cached_hw_id
    if _cached_hw_id is not None:
        return None if _cached_hw_id is _HW_UNKNOWN else _cached_hw_id
    from serial_comm import serial_sender
    try:
        hw_id = serial_sender.detect_hardware(timeout=3)
        if hw_id:
            _cached_hw_id = hw_id
            log.info("Detected hardware: %s", hw_id)
            return hw_id
        _cached_hw_id = _HW_UNKNOWN
    except Exception:
        _cached_hw_id = _HW_UNKNOWN
    return None


def _clear_hw_cache():
    global _cached_hw_id
    _cached_hw_id = None


# ── Vision API helpers ─────────────────────────────────────────

def _vision_sensors():
    """Return the (mutable) list of vision sensors from app config."""
    if _app is None:
        return []
    return _app.cfg.setdefault("plugins", {}).setdefault("vision", {}).setdefault("sensors", [])


def _save_vision_config():
    if _app is None:
        return
    from config import save_config
    save_config(_app.cfg)


def _normalize_sensor(body, existing=None):
    import time as _t
    sensor = dict(body or {})
    if not sensor.get("id"):
        ids = {s.get("id") for s in (existing or [])}
        n = len(ids) + 1
        while f"vs_{n}" in ids:
            n += 1
        sensor["id"] = f"vs_{n}"
    sensor.setdefault("enabled", True)
    sensor.setdefault("mode", "color_percentage")
    sensor.setdefault("color", "#ff0000")
    sensor.setdefault("pixel", {"x_pct": 50, "y_pct": 50})
    sensor.setdefault("tolerance", 40)
    sensor.setdefault("threshold", 30.0)
    sensor.setdefault("direction", "below")
    sensor.setdefault("poll_rate", 1.0)
    sensor.setdefault("cooldown_s", 10.0)
    sensor.setdefault("output_display", True)
    sensor.setdefault("flash_name", False)
    sensor.setdefault("require_foreground", False)
    sensor.setdefault("created", int(_t.time()))
    return sensor


def _merge_vision_config(envelope):
    """Merge the generic plugin-page envelope into the stored vision config,
    preserving the sensor list and other runtime keys."""
    existing = {}
    if _app is not None:
        existing = _app.cfg.get("plugins", {}).get("vision", {})
    merged = dict(existing or {})
    if not isinstance(envelope, dict):
        return merged
    if "enabled" in envelope:
        merged["enabled"] = envelope["enabled"]
    if "outputs" in envelope:
        merged["outputs"] = envelope["outputs"]
    cfg = envelope.get("config")
    if isinstance(cfg, dict):
        for k, v in cfg.items():
            if k not in ("enabled", "outputs"):
                merged[k] = v
    return merged


def _get_vision_sensors():
    import plugin_manager
    sensors = list(_vision_sensors())
    live = {"state": {}, "sensors": []}
    inst = plugin_manager.get("vision")
    if inst and hasattr(inst, "poll"):
        try:
            live = inst.poll()
        except Exception:
            pass
    return {"sensors": sensors, "live": live}


def _get_volume():
    import win_volume
    try:
        return win_volume.get_active_app_state()
    except Exception as e:
        log.warning("[http] volume query failed: %s", e)
        return {"app": None, "volume": None}


def start_http(port=15502):
    os.makedirs(_HTML_DIR, exist_ok=True)
    host = _bind_host()
    handler = partial(_RequestHandler, directory=_HTML_DIR)
    server = ThreadingHTTPServer((host, port), handler)
    log.info("HTTP server listening on %s:%d (serving %s)", host, port, _HTML_DIR)
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
