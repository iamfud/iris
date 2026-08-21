"""WebSocket bridge — broadcasts notification data to Iris plugin.

Also runs an HTTP server to serve the settings HTML UI and plugin API.
"""

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import socket
import ssl
import threading
import time
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial

import websockets

import win_volume

log = logging.getLogger("iris.ws_bridge")

CLIENTS = set()
_loop = None
_app = None

# per-path app icon PNG bytes (extracted once, served to the web panel fast)
_APP_ICON_CACHE = {}

# Per-process auth token. Generated once at import (fresh each launch) and
# required on every /api/* request from non-local peers. It is carried by
# the QR pairing URL: scanning it authorizes a phone to become a paired
# device. It is only ever embedded in the loopback-served QR image, never in
# API JSON responses or the static pages.
_HTTP_TOKEN = secrets.token_urlsafe(32)

# Long-lived device sessions created by scanning the QR.  Persisted to disk so a
# panel restart does not log mobile devices back out.  Tokens are stored
# only as SHA-256 hashes so the file is useless if it leaks.
_DEVICE_TTL = 365 * 24 * 3600
_DEVICES = {}
_last_devices_save = 0.0


def _devices_path():
    try:
        from config import config_path as _cp
        return os.path.join(os.path.dirname(_cp()), "devices.json")
    except Exception:
        return os.path.join(
            os.path.dirname(os.path.abspath(__file__)), "devices.json")


def _load_devices():
    try:
        with open(_devices_path()) as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k, v in data.items():
                if not isinstance(v, dict):
                    # Legacy file: values were plain expiry timestamps.
                    v = {"exp": v, "ua": "", "created": None, "last_seen": None}
                _DEVICES[k] = v
    except Exception:
        pass


def _save_devices():
    try:
        with open(_devices_path(), "w") as f:
            json.dump(_DEVICES, f, indent=2)
    except Exception:
        pass


def _touch_device(tok_hash):
    """Refresh a device's last-seen timestamp (throttled disk writes)."""
    global _last_devices_save
    rec = _DEVICES.get(tok_hash)
    if not isinstance(rec, dict):
        return
    rec["last_seen"] = time.time()
    now = time.time()
    if now - _last_devices_save >= 30:
        _last_devices_save = now
        _save_devices()


def _ua_device_name(ua):
    """Best-effort friendly name derived from the device's User-Agent."""
    if not ua:
        return "Paired device"
    low = ua.lower()
    if "ipad" in low:
        return "iPad"
    if "iphone" in low:
        return "iPhone"
    if "android" in low:
        m = re.search(r";\s*([^;\s()/]+?)\s+Build/", ua)
        if m:
            return m.group(1).strip()
        return "Android device"
    if "macintosh" in low or "mac os" in low:
        return "Mac"
    if "windows" in low:
        return "Windows PC"
    if "linux" in low:
        return "Linux"
    if "pywebview" in low:
        return "Iris Panel"
    return "Connected device"


def _get_devices():
    """Return non-sensitive metadata for every unexpired paired device."""
    now = time.time()
    out = []
    for h, rec in _DEVICES.items():
        exp = rec.get("exp") if isinstance(rec, dict) else rec
        if exp is None or now > exp:
            continue
        if isinstance(rec, dict):
            out.append({
                "id": h,
                "name": _ua_device_name(rec.get("ua", "")),
                "ua": rec.get("ua", ""),
                "created": rec.get("created"),
                "last_seen": rec.get("last_seen"),
            })
        else:
            out.append({
                "id": h, "name": "Paired device", "ua": "",
                "created": None, "last_seen": None,
            })
    out.sort(key=lambda d: d.get("last_seen") or 0, reverse=True)
    return out


def _token_hash(tok):
    return hashlib.sha256((tok or "").encode("utf-8")).hexdigest()


_load_devices()

_HTML_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), os.pardir, "HTML")


def register_app(app):
    """Register the IrisApp instance so the HTTP API can access config/serial."""
    global _app
    _app = app


# ── Auth helpers ──────────────────────────────────────────────

def _is_loopback_address(ip):
    """True for loopback source addresses (127.0.0.0/8 or ::1)."""
    try:
        if not ip:
            return False
        return ip == "::1" or ip.startswith("127.")
    except Exception:
        return False


def _valid_session(tok):
    """True when tok is a valid paired-device session cookie."""
    if not tok:
        return False
    dex = _DEVICES.get(_token_hash(tok))
    if dex is not None:
        exp = dex.get("exp") if isinstance(dex, dict) else dex
        if exp is None or time.time() > exp:
            _DEVICES.pop(_token_hash(tok), None)
            _save_devices()
            return False
        _touch_device(_token_hash(tok))
        return True
    return False


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
    """Reject WS connections from non-local peers without the auth token."""
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
    try:
        peer = getattr(connection, "remote_address", None)
        peer = peer[0] if peer else ""
    except Exception:
        peer = ""
    if _is_loopback_address(peer):
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
        if _app is not None:
            if _app.cfg.get("lan_access", True):
                return "0.0.0.0"
        else:
            from config import load_config
            if load_config().get("lan_access", True):
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


def _lan_pair_url():
    """Pairing URL encoded in the on-screen QR code."""
    host = _lan_ip()
    if _is_loopback_mode():
        host = "127.0.0.1"
    return "http://%s:15502/pair?token=%s" % (host, _HTTP_TOKEN)


def _qr_bytes():
    """Render the one-time pairing URL as a QR code PNG."""
    import io
    try:
        import qrcode
    except ImportError:
        return None
    try:
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(_lan_pair_url())
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

    def _session_cookie(self):
        raw = self.headers.get("Cookie", "")
        for part in raw.split(";"):
            part = part.strip()
            if part.startswith("iris_session="):
                return part[len("iris_session="):]
        hdr = self.headers.get("X-Iris-Session", "") or self.headers.get("X-Iris-Token", "")
        if hdr:
            return hdr
        if "?" in self.path:
            from urllib.parse import urlparse, parse_qs
            try:
                qs = parse_qs(urlparse(self.path).query)
                if "session" in qs and qs["session"]:
                    return qs["session"][0]
            except Exception:
                pass
        return ""

    def _is_loopback_peer(self):
        """True when the TCP peer is on this machine (desktop panel window)."""
        try:
            return _is_loopback_address(self.client_address[0])
        except Exception:
            return False

    def _authorized(self):
        """True when the request is allowed to reach the panel and API.

        Validates session cookie, X-Iris-Token header, or loopback requests
        (ensuring Origin header is not an external web domain).
        """
        provided = self.headers.get("X-Iris-Token", "")
        if provided and hmac.compare_digest(provided, _HTTP_TOKEN):
            return True
        if _valid_session(self._session_cookie()):
            return True

        try:
            if _is_loopback_address(self.client_address[0]):
                origin = self.headers.get("Origin", "")
                if origin:
                    from urllib.parse import urlparse
                    try:
                        op = urlparse(origin)
                        if op.hostname not in ("127.0.0.1", "localhost", "::1"):
                            return False
                    except Exception:
                        return False
                return True
        except Exception:
            pass

        return False

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

    _CSP = (
        "default-src 'none'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; "
        "font-src 'self' data: https://fonts.gstatic.com; "
        "img-src 'self' data: blob:; "
        "connect-src 'self' https://fonts.googleapis.com https://fonts.gstatic.com; "
        "media-src 'self'; "
        "frame-src 'self'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-ancestors 'self'"
    )

    def end_headers(self):
        try:
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
        except Exception:
            pass
        try:
            self.send_header("Content-Security-Policy", self._CSP)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN")
            self.send_header("Referrer-Policy", "no-referrer")
        except Exception:
            pass
        super().end_headers()

    def do_GET(self):
        # Library images are the user's own local files; img tags can't carry
        # auth headers, so serve these with host-only protection only.
        if self.path.startswith("/api/library/image/"):
            if not self._host_ok():
                self._reject_unauthorized()
                return
            self._handle_library_image(self.path[len("/api/library/image/"):])
            return
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
            self._send_json(_get_config(self._is_loopback_peer()))
        elif self.path == "/api/status":
            self._send_json(_get_device_status())
        elif self.path == "/api/settings/pages":
            self._send_json(_get_settings_pages())
        elif self.path == "/api/network/qr":
            if not self._is_loopback_peer():
                self._send_json({"ok": False})
            else:
                self._serve_network_qr()
        elif self.path == "/api/devices":
            if not self._is_loopback_peer():
                self._send_json({"ok": False})
            else:
                self._send_json({"ok": True, "devices": _get_devices()})
        elif self.path == "/api/keyboard/devices":
            self._handle_keyboard_devices()
        elif self.path == "/api/sounds":
            self._send_json(_get_sounds())
        elif self.path.startswith("/api/sounds/preview/"):
            self._handle_sound_preview(self.path.split("/")[-1])
        elif self.path == "/api/sounds/stop":
            self._handle_sound_stop()
        elif self.path == "/api/vision/sensors":
            self._send_json(_get_vision_sensors())
        elif self.path == "/api/screenshot/latest":
            self._handle_screenshot_latest()
        elif self.path == "/api/library/items":
            self._handle_library_items()
        elif self.path.startswith("/api/library/sidecar/"):
            self._handle_library_get_sidecar(self.path[len("/api/library/sidecar/"):])
        elif self.path.startswith("/api/library/note/"):
            self._handle_library_get_note(self.path[len("/api/library/note/"):])
        elif self.path == "/api/library/running_apps":
            self._handle_library_running_apps()
        elif self.path == "/api/volume/master":
            self._send_json(_get_master_volume())
        elif self.path == "/api/volume":
            self._send_json(_get_volume())
        elif self.path == "/api/panel":
            self._send_json(_get_panel())
        elif self.path == "/api/panel/live":
            self._send_json(_get_panel_live())
        elif self.path == "/api/panel/password/status":
            self._handle_password_status()
        elif self.path == "/api/panel/entities":
            self._handle_panel_entities()
        elif self.path.startswith("/api/panel/icon-meta"):
            self._handle_panel_icon_meta()
        elif self.path.startswith("/api/panel/icon"):
            self._handle_panel_icon()
        elif self.path.startswith("/api/mdi/search"):
            self._handle_mdi_search()
        elif self.path == "/api/mdi/font":
            self._serve_mdi_font()
        elif self.path.startswith("/api/mdi/codepoints"):
            self._handle_mdi_codepoints()
        elif self.path.startswith("/api/media/players"):
            self._handle_media_players()
        elif self.path.startswith("/api/media/art"):
            self._handle_media_art()
        elif self.path.startswith("/api/dialog/browse"):
            self._handle_dialog_browse()
        elif self.path == "/api/notifications" or self.path.startswith("/api/notifications?"):
            self._handle_get_notifications()
        elif self.path.startswith("/media/"):
            self._serve_media(self.path[7:])
        elif self.path.startswith("/pair"):
            self._handle_pair()
        elif self.path.split("?")[0] in ("/", "/index.html", "/login"):
            self._serve_index()
        elif self.path.split("?")[0] in ("/Iris.apk", "/download"):
            self._serve_apk()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path == "/login":
            self._handle_login()
            return
        if self.path == "/api/devices/revoke":
            self._handle_device_revoke()
            return
        if self.path.startswith("/api/"):
            if not self._host_ok() or not self._authorized():
                self._reject_unauthorized()
                return
        if self.path == "/api/config":
            self._handle_save_config()
        elif self.path == "/api/keyboard/target_device":
            self._handle_keyboard_set_target()
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
        elif self.path == "/api/notifications/delete":
            self._handle_notification_delete()
        elif self.path == "/api/notifications/clear":
            self._handle_notification_clear()
        elif self.path == "/api/portal/reload":
            self._handle_portal_reload()
        elif self.path == "/api/notifications/archive":
            self._handle_notification_archive()
        elif self.path == "/api/notifications/archive-all":
            self._handle_notification_archive_all()
        elif self.path == "/api/notifications/rule":
            self._handle_notification_rule()
        elif self.path == "/api/notifications/settings":
            self._handle_notification_settings()
        elif self.path == "/api/volume/master":
            self._handle_master_volume_set()
        elif self.path == "/api/volume/session":
            self._handle_session_volume_set()
        elif self.path == "/api/volume":
            self._handle_volume_set()
        elif self.path == "/api/panel":
            self._handle_save_panel()
        elif self.path == "/api/panel/export_buttons":
            self._handle_panel_export_buttons()
        elif self.path == "/api/panel/action":
            self._handle_panel_action()
        elif self.path == "/api/panel/brightness":
            self._handle_panel_brightness()
        elif self.path == "/api/panel/core":
            self._handle_panel_core()
        elif self.path == "/api/panel/password":
            self._handle_save_panel_password()
        elif self.path == "/api/open_url":
            self._handle_open_url()
        elif self.path.startswith("/api/library/sidecar/"):
            self._handle_library_save_sidecar(self.path[len("/api/library/sidecar/"):])
        elif self.path == "/api/library/note":
            self._handle_library_save_note()
        elif self.path.startswith("/api/library/delete/"):
            self._handle_library_delete(self.path[len("/api/library/delete/"):])
        else:
            self.send_error(404)

    def _handle_keyboard_devices(self):
        try:
            from keyboard_service import keyboard_service
            self._send_json({
                "ok": True,
                "driver_status": keyboard_service.driver_status,
                "target_device": keyboard_service.target_device,
                "devices": keyboard_service.get_devices()
            })
        except Exception as ex:
            self._send_json({"ok": False, "error": str(ex)})

    def _handle_keyboard_set_target(self):
        try:
            body = self._read_json()
            slot = int(body.get("slot", 1))
            from keyboard_service import keyboard_service
            keyboard_service.set_target_device(slot)
            self._send_json({"ok": True, "target_device": keyboard_service.target_device})
        except Exception as ex:
            self._send_json({"ok": False, "error": str(ex)})


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
        """Serve the one-time pairing QR (loopback-only, auth required).

        Encoding a fresh single-use pairing URL lets a phone scan it to
        connect without a password.  Only loopback peers can fetch the image,
        so the QR code never leaves this PC over the network.
        """
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

    def _handle_pair(self):
        """Authorize a phone via the QR-carried access token.

        Scanning the on-screen QR opens /pair?token=<access-token> here. If
        the token matches, the phone is registered as a persistent paired
        device (long-lived HttpOnly cookie backed by the on-disk device store)
        and redirected to the panel.
        """
        if not self._host_ok():
            self._reject_unauthorized()
            return
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        token = ""
        for part in query.split("&"):
            if part.startswith("token="):
                token = part[len("token="):]
        if not isinstance(token, str) or not token or not hmac.compare_digest(token, _HTTP_TOKEN):
            body = b'{"ok":false,"error":"invalid access token"}'
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        tok = secrets.token_urlsafe(32)
        ua = self.headers.get("User-Agent", "")
        existing_key = None
        for k, d in list(_DEVICES.items()):
            if isinstance(d, dict) and d.get("ua") == ua:
                existing_key = k
                break
        if existing_key:
            _DEVICES.pop(existing_key, None)

        _DEVICES[_token_hash(tok)] = {
            "exp": time.time() + _DEVICE_TTL,
            "ua": ua,
            "created": time.time(),
            "last_seen": time.time(),
        }
        _save_devices()
        self.send_response(302)
        self.send_header("Location", "/")
        self.send_header("Set-Cookie",
                         f"iris_session={tok}; SameSite=Lax; Path=/; Max-Age={_DEVICE_TTL}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _handle_login(self):
        """Handle POST /login with panel password verification."""
        try:
            import panel_auth
        except Exception:
            self._send_json({"ok": False, "error": "password_unavailable"}, status=500)
            return

        if not panel_auth.password_available():
            self._send_json({"ok": False, "error": "password_unavailable"}, status=400)
            return

        length = int(self.headers.get("Content-Length", 0))
        body_raw = self.rfile.read(length) if length > 0 else b""
        try:
            body = json.loads(body_raw.decode("utf-8")) if body_raw else {}
        except Exception:
            body = {}

        password = body.get("password", "")
        if not password:
            self._send_json({"ok": False, "error": "empty_password"}, status=400)
            return

        cfg = _app.cfg if _app is not None else {}
        if not cfg:
            try:
                from config import load_config
                cfg = load_config()
            except Exception:
                pass

        stored_hash = cfg.get("panel_password_hash", "")
        if not stored_hash:
            self._send_json({"ok": False, "error": "no_password"}, status=400)
            return

        if not panel_auth.verify_password(stored_hash, password):
            self._send_json({"ok": False, "error": "incorrect_password"}, status=401)
            return

        ua = self.headers.get("User-Agent", "")
        existing_key = None
        for k, d in list(_DEVICES.items()):
            if isinstance(d, dict) and d.get("ua") == ua:
                existing_key = k
                break
        if existing_key:
            _DEVICES.pop(existing_key, None)

        tok = secrets.token_urlsafe(32)
        _DEVICES[_token_hash(tok)] = {
            "exp": time.time() + _DEVICE_TTL,
            "ua": ua,
            "created": time.time(),
            "last_seen": time.time(),
        }
        _save_devices()

        res_bytes = json.dumps({"ok": True, "token": tok}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(res_bytes)))
        self.send_header("Set-Cookie", f"iris_session={tok}; SameSite=Lax; Path=/; Max-Age={_DEVICE_TTL}")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(res_bytes)

    def _handle_password_status(self):
        """Return {"ok": true, "available": bool, "set": bool} for password configurator."""
        try:
            import panel_auth
            avail = panel_auth.password_available()
        except Exception:
            avail = False

        cfg = _app.cfg if _app is not None else {}
        if not cfg:
            try:
                from config import load_config
                cfg = load_config()
            except Exception:
                pass

        has_pw = bool(cfg.get("panel_password_hash"))
        self._send_json({"ok": True, "available": avail, "set": has_pw})

    def _handle_save_panel_password(self):
        """Handle POST /api/panel/password to set or update the Argon2id hash."""
        try:
            import panel_auth
        except Exception:
            self._send_json({"ok": False, "error": "password_unavailable"})
            return

        if not panel_auth.password_available():
            self._send_json({"ok": False, "error": "password_unavailable"})
            return

        length = int(self.headers.get("Content-Length", 0))
        body_raw = self.rfile.read(length) if length > 0 else b""
        try:
            body = json.loads(body_raw.decode("utf-8")) if body_raw else {}
        except Exception:
            body = {}

        new_pw = (body.get("password") or "").strip()
        cur_pw = body.get("current") or body.get("current_password") or ""

        cfg = _app.cfg if _app is not None else {}
        if not cfg:
            try:
                from config import load_config
                cfg = load_config()
            except Exception:
                pass

        stored_hash = cfg.get("panel_password_hash", "")

        if stored_hash:
            if not cur_pw or not panel_auth.verify_password(stored_hash, cur_pw):
                self._send_json({"ok": False, "error": "incorrect current password"})
                return

        if not new_pw or len(new_pw) < panel_auth.MIN_PASSWORD_LEN:
            self._send_json({"ok": False, "error": "too_short", "min_length": panel_auth.MIN_PASSWORD_LEN})
            return

        from config import save_config
        new_hash = panel_auth.hash_password(new_pw)
        if _app is not None:
            _app.cfg["panel_password_hash"] = new_hash
            save_config(_app.cfg)
        else:
            from config import load_config
            c = load_config()
            c["panel_password_hash"] = new_hash
            save_config(c)

        self._send_json({"ok": True, "set": True})

    def _handle_get_notifications(self):
        try:
            import notifications_store
            data = notifications_store.get_notifications()
            self._send_json({"ok": True, **data})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_notification_delete(self):
        try:
            body = self._read_json() or {}
            notif_id = body.get("id")
            if not notif_id:
                self._send_json({"ok": False, "error": "missing id"})
                return
            import notifications_store
            res = notifications_store.delete_notification(notif_id)
            self._send_json({"ok": res})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_notification_clear(self):
        try:
            body = self._read_json() or {}
            include_archived = bool(body.get("include_archived", False))
            import notifications_store
            res = notifications_store.delete_all(include_archived)
            self._send_json({"ok": res})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_notification_archive(self):
        try:
            body = self._read_json() or {}
            notif_id = body.get("id")
            archived = bool(body.get("archived", True))
            if not notif_id:
                self._send_json({"ok": False, "error": "missing id"})
                return
            import notifications_store
            res = notifications_store.set_archived(notif_id, archived)
            self._send_json({"ok": res})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_notification_archive_all(self):
        try:
            import notifications_store
            res = notifications_store.archive_all()
            self._send_json({"ok": res})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_notification_rule(self):
        try:
            body = self._read_json() or {}
            source = body.get("source")
            rule = body.get("rule", "normal")
            if not source:
                self._send_json({"ok": False, "error": "missing source"})
                return
            import notifications_store
            notifications_store.set_source_rule(source, rule)
            self._send_json({"ok": True, "rules": notifications_store.get_source_rules()})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _handle_notification_settings(self):
        try:
            body = self._read_json() or {}
            max_stored = body.get("max_stored")
            if max_stored is not None:
                import notifications_store
                notifications_store.set_max_stored(max_stored)
            self._send_json({"ok": True})
        except Exception as e:
            self._send_json({"ok": False, "error": str(e)})

    def _serve_index(self):
        """Serve the settings panel, or the pairing info page if unauthorized."""
        if not self._authorized():
            self._serve_login()
            return
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
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def _serve_login(self):
        """Serve the pairing info page for unauthorized LAN peers."""
        login_path = os.path.join(self.directory, "login.html")
        if not os.path.isfile(login_path):
            self.send_error(404)
            return
        try:
            with open(login_path, "rb") as f:
                html = f.read()
        except Exception:
            self.send_error(500)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def _serve_apk(self):
        """Serve the compiled Android APK file with attachment headers."""
        apk_path = os.path.join(self.directory, "Iris.apk")
        if not os.path.isfile(apk_path):
            self.send_error(404, "Iris.apk not found")
            return
        try:
            with open(apk_path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.android.package-archive")
            self.send_header("Content-Disposition", "attachment; filename=\"Iris.apk\"")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            log.warning("[http] failed to serve APK: %s", e)
            self.send_error(500)

    def _handle_device_revoke(self):
        """Revoke a paired device by id. Loopback-only (desktop panel)."""
        if not self._is_loopback_peer():
            self._send_json({"ok": False, "error": "forbidden"})
            return
        try:
            payload = self._read_json()
        except Exception:
            self.send_error(400)
            return
        dev_id = payload.get("id")
        if dev_id and _DEVICES.pop(dev_id, None):
            _save_devices()
            self._send_json({"ok": True})
        else:
            self._send_json({"ok": False, "error": "unknown device"})

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

    def _handle_portal_reload(self):
        try:
            broadcast({"type": "reload", "hard": True})
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("[http] portal reload broadcast failed: %s", e)
            self.send_error(500, str(e))

    def _handle_save_config(self):
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length)) if length else {}
            if _app is None:
                self.send_error(503, "App not registered")
                return
            from config import save_config
            # MAX7219 brightness is applied live to the hardware (saved + pushed
            # to the display), not just stored — do it before the generic cfg
            # update so _set_brightness still sees the previous value.
            if "brightness" in body:
                try:
                    _app._set_brightness(max(0, min(4, int(body["brightness"]))))
                except Exception:
                    log.warning("[http] failed to apply brightness: %s", body.get("brightness"))
            body = {k: v for k, v in body.items()
                    if k not in ("http_token", "lan_url",
                                 "panel_password", "panel_password_hash",
                                 "panel_password_salt")}
            _app.cfg.update(body)
            save_config(_app.cfg)
            self._push_config_to_device(body)
            if "theme" in body:
                broadcast({"type": "theme", "theme": body["theme"], "reload": True})
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

        if not hasattr(self, "_SERIAL_PUSH_LOCK"):
            self._SERIAL_PUSH_LOCK = threading.Lock()

        def _send():
            with self._SERIAL_PUSH_LOCK:
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

    def _handle_screenshot_latest(self):
        """Return the most recent screenshot captured by the Tk dialog."""
        if _app is None:
            self._send_json({"available": False})
            return
        data = getattr(_app, "screenshot_last", None)
        if not data:
            self._send_json({"available": False})
            return
        self._send_json({"available": True, **data})

    # ── Library ────────────────────────────────────────────────────────────

    def _library_folder(self):
        """Return the resolved screenshot / library folder path."""
        folder = ""
        if _app is not None:
            try:
                folder = (_app.cfg.get("screenshot_dir") or "").strip()
            except Exception:
                pass
        if not folder:
            folder = os.path.join(os.path.expanduser("~"), "Documents", "Iris", "Screenshots")
        return os.path.abspath(folder)

    def _parse_library_filename(self, fname):
        """Extract app name and timestamp from an iris_* filename.

        New format: iris_APPNAME_YYYYMMDD_HHMMSS.png
        Old format: iris_YYYYMMDD_HHMMSS.png  (app → 'unknown')
        Note format: iris_note_APPNAME_YYYYMMDD_HHMMSS.txt
        """
        import re as _re
        # Note file
        m = _re.match(r'^iris_note_(.+)_(\d{8}_\d{6})\.txt$', fname)
        if m:
            return {"type": "note", "app": m.group(1), "ts_str": m.group(2)}
        # New screenshot format
        m = _re.match(r'^iris_([a-z0-9_]+)_(\d{8})_(\d{6})\.png$', fname)
        if m:
            app = m.group(1)
            ts_str = m.group(2) + "_" + m.group(3)
            return {"type": "screenshot", "app": app, "ts_str": ts_str}
        # Old screenshot format iris_YYYYMMDD_HHMMSS.png
        m = _re.match(r'^iris_(\d{8})_(\d{6})\.png$', fname)
        if m:
            ts_str = m.group(1) + "_" + m.group(2)
            return {"type": "screenshot", "app": "unknown", "ts_str": ts_str}
        return None

    def _ts_from_str(self, ts_str):
        """Convert YYYYMMDD_HHMMSS → unix timestamp."""
        try:
            import time as _t
            return _t.mktime(_t.strptime(ts_str, "%Y%m%d_%H%M%S"))
        except Exception:
            return 0.0

    def _sidecar_path(self, folder, img_fname):
        base = os.path.splitext(img_fname)[0]
        return os.path.join(folder, base + ".json")

    def _handle_library_items(self):
        """List all screenshots and notes in the library folder."""
        folder = self._library_folder()
        items = []
        try:
            if not os.path.isdir(folder):
                self._send_json({"items": []})
                return

            # Collect all filenames; track PNG basenames to detect orphaned sidecars
            all_files = os.listdir(folder)
            png_basenames = {
                os.path.splitext(f)[0]
                for f in all_files
                if f.lower().endswith(".png")
            }

            for fname in all_files:
                meta = self._parse_library_filename(fname)

                # Unrecognised PNG — show as orphan using file mtime
                if meta is None:
                    if fname.lower().endswith(".png"):
                        fpath = os.path.join(folder, fname)
                        ts = os.path.getmtime(fpath) if os.path.isfile(fpath) else 0.0
                        sc_path = self._sidecar_path(folder, fname)
                        title = ""
                        if os.path.isfile(sc_path):
                            try:
                                with open(sc_path, encoding="utf-8") as f:
                                    sc = json.load(f)
                                title = sc.get("title", "")
                            except Exception:
                                pass
                        items.append({
                            "type": "screenshot",
                            "filename": fname,
                            "app": "orphan",
                            "ts": ts,
                            "title": title,
                        })
                    continue

                ts = self._ts_from_str(meta["ts_str"])


                if meta["type"] == "screenshot":
                    # Read title from sidecar if present
                    sc_path = self._sidecar_path(folder, fname)
                    title = ""
                    if os.path.isfile(sc_path):
                        try:
                            with open(sc_path, encoding="utf-8") as f:
                                sc = json.load(f)
                            title = sc.get("title", "")
                        except Exception:
                            pass
                    items.append({
                        "type": "screenshot",
                        "filename": fname,
                        "app": meta["app"],
                        "ts": ts,
                        "title": title,
                    })

                elif meta["type"] == "note":
                    preview = ""
                    fpath = os.path.join(folder, fname)
                    try:
                        with open(fpath, encoding="utf-8") as f:
                            content = f.read(200)
                        preview = content.split("\n")[0][:80]
                    except Exception:
                        pass
                    items.append({
                        "type": "note",
                        "filename": fname,
                        "app": meta["app"],
                        "ts": ts,
                        "preview": preview,
                    })

            # Auto-delete orphaned sidecar JSON files
            for fname in all_files:
                if fname.lower().endswith(".json"):
                    base = os.path.splitext(fname)[0]
                    if base not in png_basenames:
                        try:
                            os.remove(os.path.join(folder, fname))
                            log.info("library: removed orphaned sidecar %s", fname)
                        except Exception:
                            pass

            # Sort newest first
            items.sort(key=lambda x: x["ts"], reverse=True)
            self._send_json({"items": items})
        except Exception as e:
            log.warning("library items error: %s", e)
            self._send_json({"items": []})

    def _handle_library_image(self, filename):
        """Serve a PNG from the library folder."""
        from urllib.parse import unquote
        filename = unquote(filename.split("?")[0])  # strip query string, decode %xx
        filename = os.path.basename(filename)
        if not filename.lower().endswith(".png"):
            self.send_error(400)
            return
        path = os.path.join(self._library_folder(), filename)
        if not os.path.isfile(path):
            self.send_error(404)
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)
        except Exception as e:
            log.warning("library image serve error: %s", e)
            self.send_error(500)

    def _handle_library_get_sidecar(self, filename):
        """Return sidecar JSON for a screenshot (empty object if none exists)."""
        filename = os.path.basename(filename)
        sc_path = self._sidecar_path(self._library_folder(), filename)
        if not os.path.isfile(sc_path):
            self._send_json({})
            return
        try:
            with open(sc_path, encoding="utf-8") as f:
                self._send_json(json.load(f))
        except Exception:
            self._send_json({})

    def _handle_library_save_sidecar(self, filename):
        """Save sidecar JSON for a screenshot."""
        filename = os.path.basename(filename)
        folder = self._library_folder()
        img_path = os.path.join(folder, filename)
        if not os.path.isfile(img_path):
            self.send_error(404)
            return
        try:
            body = self._read_json()
            sc_path = self._sidecar_path(folder, filename)
            # Preserve existing annotation data; only update allowed keys
            existing = {}
            if os.path.isfile(sc_path):
                try:
                    with open(sc_path, encoding="utf-8") as f:
                        existing = json.load(f)
                except Exception:
                    pass
            existing["title"] = str(body.get("title", existing.get("title", "")))
            with open(sc_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False)
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("library sidecar save error: %s", e)
            self.send_error(500)

    def _handle_library_get_note(self, filename):
        """Return the content of a note file."""
        filename = os.path.basename(filename)
        path = os.path.join(self._library_folder(), filename)
        if not os.path.isfile(path):
            self._send_json({"content": "", "app": "", "title": ""})
            return
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            # First line is the title (prefixed "title:"), rest is body
            lines = content.split("\n", 2)
            title = ""
            body = content
            if lines and lines[0].startswith("title:"):
                title = lines[0][6:].strip()
                body = "\n".join(lines[1:]).lstrip("\n")
            meta = self._parse_library_filename(filename) or {}
            self._send_json({"content": body, "title": title, "app": meta.get("app", "")})
        except Exception as e:
            log.warning("library note read error: %s", e)
            self.send_error(500)

    def _handle_library_save_note(self):
        """Create or overwrite a note file."""
        import time as _t
        import re as _re
        try:
            body = self._read_json()
            app = body.get("app", "general") or "general"
            app = _re.sub(r'[^a-z0-9]+', '_', app.lower()).strip('_') or "general"
            title = str(body.get("title", "")).strip()
            content = str(body.get("content", ""))
            filename = body.get("filename", "")

            folder = self._library_folder()
            os.makedirs(folder, exist_ok=True)

            if not filename:
                ts = _t.strftime("%Y%m%d_%H%M%S")
                filename = "iris_note_%s_%s.txt" % (app, ts)

            path = os.path.join(folder, os.path.basename(filename))
            with open(path, "w", encoding="utf-8") as f:
                f.write("title:%s\n%s" % (title, content))
            self._send_json({"ok": True, "filename": os.path.basename(path)})
        except Exception as e:
            log.warning("library note save error: %s", e)
            self.send_error(500)

    def _handle_library_delete(self, filename):
        """Delete a library item (PNG + sidecar, or note txt)."""
        filename = os.path.basename(filename)
        folder = self._library_folder()
        try:
            path = os.path.join(folder, filename)
            if not os.path.isfile(path):
                self.send_error(404)
                return
            os.remove(path)
            # Also remove sidecar if it's a PNG
            if filename.lower().endswith(".png"):
                sc = self._sidecar_path(folder, filename)
                if os.path.isfile(sc):
                    os.remove(sc)
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("library delete error: %s", e)
            self.send_error(500)

    def _handle_library_running_apps(self):
        """Return a list of currently running process names for the note app picker."""
        try:
            import psutil
            seen = set()
            apps = []
            for proc in psutil.process_iter(["name"]):
                try:
                    name = proc.info["name"] or ""
                    import re as _re
                    key = _re.sub(r'\.exe$', '', name, flags=_re.IGNORECASE).lower()
                    key = _re.sub(r'[^a-z0-9]+', '_', key).strip('_')
                    if key and key not in seen:
                        seen.add(key)
                        apps.append(key)
                except Exception:
                    pass
            apps.sort()
            self._send_json({"apps": apps})
        except Exception as e:
            log.warning("library running apps error: %s", e)
            self._send_json({"apps": []})

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

    def _handle_master_volume_set(self):
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
        ok = win_volume.set_master_volume(max(0, min(100, value)))
        self._send_json({"ok": ok})

    def _handle_session_volume_set(self):
        """Set a specific app session's volume or mute.

        Body: {"pid": int, "volume": int(0-100)} and/or {"pid": int, "mute": bool}.
        Missing pid/mode -> 400.  Unknown session -> {"ok": false}.
        """
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        try:
            pid = int(body.get("pid"))
        except (TypeError, ValueError):
            self.send_error(400, "pid must be an integer")
            return
        import win_volume
        if "mute" in body:
            ok = win_volume.set_session_mute(pid, bool(body.get("mute")))
        else:
            try:
                value = int(body.get("volume"))
            except (TypeError, ValueError):
                self.send_error(400, "volume must be an integer")
                return
            ok = win_volume.set_session_volume(pid, max(0, min(100, value)))
        self._send_json({"ok": ok})

    def _handle_save_panel(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        if _app is None:
            self.send_error(503, "App not registered")
            return
        try:
            from panel_actions import apply_panel_save
            from config import save_config
            apply_panel_save(_app.cfg, body)
            save_config(_app.cfg)
            mw = getattr(_app, "_main_win", None)
            if mw is not None and hasattr(mw, "rebuild_panel"):
                try:
                    _app._root.after(0, mw.rebuild_panel)
                except Exception:
                    pass
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("[http] save panel failed: %s", e)
            self.send_error(500, str(e))

    def _handle_panel_icon(self):
        """Extract + serve the app icon for a shortcut path (PNG, cached)."""
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            import shutil
            qs = parse_qs(urlparse(self.path).query)
            raw_p = (qs.get("path") or [""])[0]
            if not raw_p:
                self.send_error(404)
                return
            p = unquote(raw_p).strip().strip('"\'')
            p = os.path.expandvars(os.path.expanduser(p))
            if not os.path.isfile(p):
                which_p = shutil.which(p)
                if which_p and os.path.isfile(which_p):
                    p = which_p
                else:
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    cand = os.path.join(base_dir, p)
                    if os.path.isfile(cand):
                        p = cand
                    else:
                        cand_media = os.path.join(base_dir, "media", p)
                        if os.path.isfile(cand_media):
                            p = cand_media
            if not os.path.isfile(p):
                self.send_error(404)
                return
            norm = os.path.normcase(os.path.abspath(p))
            cached = _APP_ICON_CACHE.get(norm)
            if cached is None:
                from win_platform import _extract_via_ps, detect_icon_color
                img = _extract_via_ps(p, size=256)
                if img is None:
                    self.send_error(404)
                    return
                color = detect_icon_color(img)
                import io
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                blob = buf.getvalue()
                if len(_APP_ICON_CACHE) >= 100:
                    _APP_ICON_CACHE.pop(next(iter(_APP_ICON_CACHE)), None)
                _APP_ICON_CACHE[norm] = (blob, color)
            else:
                blob, color = cached
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(blob)))
            if color:
                self.send_header("X-Detected-Color", color)
                self.send_header("Access-Control-Expose-Headers", "X-Detected-Color")
            self.end_headers()
            self.wfile.write(blob)
        except Exception as e:
            log.warning("[http] app icon extraction failed: %s", e)
            self.send_error(500)

    def _handle_panel_icon_meta(self):
        """Return detected icon color metadata for an executable or image path."""
        try:
            from urllib.parse import urlparse, parse_qs, unquote
            import shutil
            qs = parse_qs(urlparse(self.path).query)
            raw_p = (qs.get("path") or [""])[0]
            if not raw_p:
                self._send_json({"ok": False, "error": "missing path"})
                return
            p = unquote(raw_p).strip().strip('"\'')
            p = os.path.expandvars(os.path.expanduser(p))
            if not os.path.isfile(p):
                which_p = shutil.which(p)
                if which_p and os.path.isfile(which_p):
                    p = which_p
                else:
                    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
                    cand = os.path.join(base_dir, p)
                    if os.path.isfile(cand):
                        p = cand
                    else:
                        cand_media = os.path.join(base_dir, "media", p)
                        if os.path.isfile(cand_media):
                            p = cand_media
            if not os.path.isfile(p):
                self._send_json({"ok": False, "error": "file not found"})
                return
            norm = os.path.normcase(os.path.abspath(p))
            cached = _APP_ICON_CACHE.get(norm)
            if cached is not None:
                _, color = cached
            else:
                from win_platform import _extract_via_ps, detect_icon_color
                img = _extract_via_ps(p, size=256)
                if img is None:
                    self._send_json({"ok": False, "error": "extraction failed"})
                    return
                color = detect_icon_color(img)
                import io
                buf = io.BytesIO()
                img.save(buf, format="PNG")
                blob = buf.getvalue()
                if len(_APP_ICON_CACHE) >= 100:
                    _APP_ICON_CACHE.pop(next(iter(_APP_ICON_CACHE)), None)
                _APP_ICON_CACHE[norm] = (blob, color)
            self._send_json({"ok": True, "path": p, "color": color})
        except Exception as e:
            log.warning("[http] icon meta extraction failed: %s", e)
            self._send_json({"ok": False, "error": str(e)})

    def _serve_mdi_font(self):
        """Serve the MDI webfont so the web panel renders the same icons as Tk."""
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mdi-webfont.ttf")
        if not os.path.isfile(path):
            self.send_error(404)
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "font/ttf")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        except Exception:
            self.send_error(500)

    def _handle_mdi_search(self):
        """Return search matches across all 7,440+ icons: ?q=xbox&cat=gamer&limit=120"""
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        q = (qs.get("q") or [""])[0]
        cat = (qs.get("cat") or [""])[0]
        try:
            limit = int((qs.get("limit") or [120])[0])
        except (TypeError, ValueError):
            limit = 120
        try:
            import mdi_icons
            results = mdi_icons.search_icons(query=q, category=cat, limit=limit)
            self._send_json({"ok": True, "icons": results})
        except Exception as ex:
            self._send_json({"ok": False, "icons": [], "error": str(ex)})

    def _handle_mdi_codepoints(self):
        """Return {"name": "<char>"} for ?names=a,b,c (missing -> null)."""
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        names = qs.get("names", [""])
        if not names:
            self._send_json({})
            return
        import mdi_icons
        result = {}
        for chunk in names:
            for n in chunk.split(","):
                n = n.strip()
                if n:
                    result[n] = mdi_icons.get_char(n)
        self._send_json(result)

    def _handle_media_players(self):
        try:
            from win_platform import detect_installed_media_players
            players = detect_installed_media_players()
            current = (_app.cfg.get("media_player_path", "") or "") if _app is not None else ""
            self._send_json({"ok": True, "players": players, "current": current})
        except Exception as e:
            log.warning("[http] detect media players failed: %s", e)
            self._send_json({"ok": False, "players": [], "current": "", "error": str(e)})

    def _handle_media_art(self):
        """Serve the currently playing album/song artwork (JPEG/PNG)."""
        art_bytes = None
        mime = "image/jpeg"
        art_id = ""
        try:
            if _app is not None and getattr(_app, "_providers", None):
                for p in _app._providers:
                    if hasattr(p, "get_artwork"):
                        art_bytes, mime, art_id = p.get_artwork()
                        break
        except Exception as ex:
            log.debug("[http] media art lookup error: %s", ex)

        if not art_bytes:
            self.send_response(404)
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", mime or "image/jpeg")
        self.send_header("Content-Length", str(len(art_bytes)))
        self.send_header("Cache-Control", "public, max-age=60")
        if art_id:
            self.send_header("ETag", f'"{art_id}"')
        self.end_headers()
        try:
            self.wfile.write(art_bytes)
        except Exception:
            pass

    def _handle_dialog_browse(self):
        """Open a native Windows file dialog to pick an .ico, .exe, .png, etc."""
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        browse_type = (qs.get("type") or ["icon"])[0]
        try:
            from win_platform import open_file_dialog, open_folder_dialog
            root = getattr(_app, "_root", None) if _app is not None else None
            if browse_type == "exe":
                path = open_file_dialog(title="Choose Executable or Shortcut", file_filter="exe", root=root)
            elif browse_type == "folder":
                path = open_folder_dialog(title="Choose Folder", root=root)
            else:
                path = open_file_dialog(title="Choose Custom Icon or Executable", file_filter="icon", root=root)
            self._send_json({"ok": True, "path": path or ""})
        except Exception as ex:
            log.warning("[http] dialog browse failed: %s", ex)
            self._send_json({"ok": False, "path": "", "error": str(ex)})

    def _handle_open_url(self):
        """Open an HTTP/HTTPS URL in the host PC's default browser."""
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return

        url = (body.get("url") or "").strip()
        if not url:
            self.send_error(400, "Missing URL")
            return

        if not (url.startswith("http://") or url.startswith("https://")):
            self.send_error(400, "Invalid URL protocol (http/https only)")
            return

        try:
            import webbrowser
            log.info("[ws_bridge] Opening URL on host PC: %s", url)
            webbrowser.open(url)
            self._send_json({"ok": True, "url": url})
        except Exception as ex:
            log.exception("[ws_bridge] Failed to open URL on PC: %s", ex)
            self.send_error(500, str(ex))

    def _handle_panel_action(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        try:
            from panel_runtime import execute_slot
            self._send_json(execute_slot(body.get("slot")))
        except Exception as e:
            log.warning("[http] panel action failed: %s", e)
            self.send_error(500, str(e))

    def _handle_panel_brightness(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        if _app is None:
            self.send_error(503, "App not registered")
            return
        try:
            value = int(body.get("brightness"))
        except (TypeError, ValueError):
            self.send_error(400, "brightness must be an integer")
            return
        try:
            _app._set_brightness(max(0, min(4, value)))
            self._send_json({"ok": True, "brightness": _app.cfg.get("brightness")})
        except Exception as e:
            log.warning("[http] set brightness failed: %s", e)
            self.send_error(500, str(e))

    def _handle_panel_core(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        if _app is None:
            self.send_error(503, "App not registered")
            return
        tile = body.get("tile")
        if tile == "display":
            cur = bool(_app.cfg.get("pc_stats_manual", False))
            try:
                _app._toggle_pc_stats(not cur)
            except Exception as e:
                log.warning("[http] pc stats toggle failed: %s", e)
            self._send_json({"ok": True, "state": not cur})
        elif tile == "overlay":
            cur = bool(getattr(_app, "_overlay", None))
            try:
                _app._root.after(0, lambda: _app._toggle_overlay(not cur))
            except Exception as e:
                log.warning("[http] overlay toggle failed: %s", e)
            self._send_json({"ok": True, "state": not cur})
        elif tile == "mic":
            try:
                from win_platform import toggle_mic_mute
                st = toggle_mic_mute()
            except Exception as e:
                log.warning("[http] mic toggle failed: %s", e)
                st = None
            self._send_json({"ok": st is not None, "state": st})
        else:
            self._send_json({"ok": False})

    def _handle_panel_export_buttons(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        if _app is None:
            self.send_error(503, "App not registered")
            return

        from panel_actions import sanitize_slot, sanitize_profiles, sanitize_board, ensure_panel_defaults
        from config import save_config

        profile_id = str(body.get("profile_id") or "__default__").strip()
        plugin_name = str(body.get("plugin") or "").strip()
        buttons = body.get("buttons") or []
        replace_all = bool(body.get("replace_all", False))
        slot_idx = body.get("slot_idx")

        slots = []
        for b in buttons:
            bid = b.get("id") or b.get("button_id")
            if not bid:
                continue
            ent_id = b.get("entity") or (f"{plugin_name}.{bid}" if plugin_name else bid)
            slot = {
                "type": "TOGGLE",
                "entity": ent_id,
                "name": b.get("name") or bid.replace("_", " ").title(),
                "plugin": plugin_name or b.get("plugin", ""),
                "button_id": bid,
                "widget_type": b.get("widget_type", "status_toggle"),
                "icon": b.get("icon") or "toggle-switch",
                "icon_off": b.get("icon_off") or "",
                "state_key": b.get("state_key") or bid,
                "labels": b.get("labels") or {},
                "colors": b.get("colors") or {},
                "hotkey": b.get("hotkey") or b.get("default_hotkey") or "",
                "show_name": True,
                "show_icon": True,
                "show_state": True,
                "description": b.get("description") or "",
            }
            s = sanitize_slot(slot)
            if s:
                slots.append(s)

        cfg = _app.cfg
        ensure_panel_defaults(cfg)

        target_name = "Default"
        if profile_id == "__default__":
            if replace_all:
                cfg["panel_board"] = slots[:12]
            else:
                board = list(cfg.get("panel_board") or [])
                if slot_idx is not None and 0 <= int(slot_idx) < 12:
                    while len(board) <= int(slot_idx):
                        board.append({"type": "EMPTY", "name": "", "icon": "border-none-variant", "color": ""})
                    if slots:
                        board[int(slot_idx)] = slots[0]
                else:
                    placed = False
                    for i in range(min(12, len(board))):
                        if board[i].get("type") == "EMPTY" and slots:
                            board[i] = slots[0]
                            placed = True
                            break
                    if not placed and len(board) < 12 and slots:
                        board.append(slots[0])
                cfg["panel_board"] = sanitize_board(board)
        else:
            profiles = cfg.get("panel_profiles") or []
            if profile_id == "__new__":
                base_id = f"prof_{plugin_name}" if plugin_name else "prof_custom"
                existing_ids = {p.get("id") for p in profiles if isinstance(p, dict)}
                new_id = base_id
                counter = 1
                while new_id in existing_ids:
                    counter += 1
                    new_id = f"{base_id}_{counter}"
                profile_id = new_id

            prof = next((p for p in profiles if isinstance(p, dict) and p.get("id") == profile_id), None)
            if not prof:
                prof_name = body.get("profile_name") or plugin_name.replace("_", " ").title()
                prof_exe = body.get("profile_exe") or ""
                prof = {
                    "id": profile_id,
                    "name": prof_name,
                    "exe": prof_exe,
                    "enabled": True,
                    "board": []
                }
                profiles.append(prof)
            target_name = prof.get("name") or profile_id

            if replace_all:
                prof["board"] = slots[:12]
            else:
                board = list(prof.get("board") or [])
                if slot_idx is not None and 0 <= int(slot_idx) < 12:
                    while len(board) <= int(slot_idx):
                        board.append({"type": "EMPTY", "name": "", "icon": "border-none-variant", "color": ""})
                    if slots:
                        board[int(slot_idx)] = slots[0]
                else:
                    placed = False
                    for i in range(min(12, len(board))):
                        if board[i].get("type") == "EMPTY" and slots:
                            board[i] = slots[0]
                            placed = True
                            break
                    if not placed and len(board) < 12 and slots:
                        board.append(slots[0])
                prof["board"] = sanitize_board(board)

            cfg["panel_profiles"] = sanitize_profiles(profiles)

        save_config(cfg)
        from panel_actions import _RESOLVE_CACHE
        _RESOLVE_CACHE["ts"] = 0.0
        _RESOLVE_CACHE["board"] = None

        self._send_json({"ok": True, "target_profile": target_name, "profile_id": profile_id, "count": len(slots)})

    def _handle_panel_entities(self):
        try:
            from panel_entities import get_entity_registry
            entities = get_entity_registry()
            self._send_json({"ok": True, "entities": entities})
        except Exception as e:
            log.warning("[http] panel entities failed: %s", e)
            self._send_json({"ok": False, "entities": []})

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
            "buttons_def": manifest.get("buttons", []),
            "preset_layout": manifest.get("preset_layout", []),
            "panel_profiles": list(_app.cfg.get("panel_profiles") or []) if _app else [],
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


def _get_config(loopback=False):
    if _app is None:
        return {}
    cfg = {k: v for k, v in _app.cfg.items()
           if not k.startswith("_") and k not in (
               "ha_token", "panel_password",
               "panel_password_salt", "panel_password_hash")}
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


def _get_panel():
    if _app is None:
        return {"panel_board": [], "actions": []}
    from panel_actions import panel_payload
    return panel_payload(_app.cfg)


def _get_panel_live():
    if _app is None:
        from panel_runtime import live_payload
        return live_payload({})
    from panel_runtime import live_payload
    return live_payload(_app.cfg)


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


def _get_master_volume():
    import win_volume
    try:
        return win_volume.get_master_state()
    except Exception as e:
        log.warning("[http] master volume query failed: %s", e)
        return {"volume": None}


def start_udp_discovery(discovery_port=15503, http_port=15502):
    """Listen for UDP broadcast queries ('IRIS_DISCOVER_REQ') and respond with server URL."""
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(("", discovery_port))
        log.info("UDP discovery listening on port %d", discovery_port)
    except Exception as e:
        log.warning("UDP discovery bind failed: %s", e)
        return

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            if data.strip() == b"IRIS_DISCOVER_REQ":
                lan_ip = _lan_ip()
                resp = f"IRIS_DISCOVER_RESP|http://{lan_ip}:{http_port}".encode("utf-8")
                sock.sendto(resp, addr)
        except Exception as e:
            log.warning("UDP discovery handle error: %s", e)
            time.sleep(0.5)


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

    # start UDP discovery service in a background thread
    threading.Thread(target=start_udp_discovery, args=(15503, http_port), daemon=True, name="udp-discovery").start()

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
