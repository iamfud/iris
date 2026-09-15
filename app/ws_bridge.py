"""WebSocket bridge — broadcasts notification data to Iris plugin.

Also runs an HTTP server to serve the settings HTML UI and plugin API.
"""

import asyncio
import collections
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import socket
import ssl
import sys
import threading
import time
from pathlib import Path
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from functools import partial

import websockets

import win_volume
import paths

log = logging.getLogger("iris.ws_bridge")

CLIENTS = set()
_loop = None
_app = None

# Cap incoming HTTP request bodies to prevent LAN-exposed memory-exhaustion (DoS).
_MAX_BODY_SIZE = 1 * 1024 * 1024

# per-path app icon PNG bytes (extracted once, served to the web panel fast)
_APP_ICON_CACHE = collections.OrderedDict()
_APP_ICON_LOCK = threading.Lock()

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

if getattr(sys, "frozen", False):
    _ROOT_DIR = sys._MEIPASS
else:
    _ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_HTML_DIR = os.path.join(_ROOT_DIR, "HTML")

# Use loose HTML/ on disk only during development if the directory actually exists.
# When frozen (packaged executable) or if HTML/ is absent, serve from in-memory embedded_assets.
_USE_DEV_ASSETS = (not getattr(sys, "frozen", False)) and os.path.isdir(_HTML_DIR)

try:
    import embedded_assets
except ImportError:
    embedded_assets = None


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
    peer = getattr(websocket, "remote_address", None)
    log.info("WS client connected from %s (%d active)", peer, len(CLIENTS))
    try:
        await websocket.wait_closed()
    finally:
        CLIENTS.discard(websocket)
        log.info("WS client disconnected from %s (%d active)", peer, len(CLIENTS))


def _ws_process_request(connection, request):
    """Reject WS connections from non-local peers without auth token or valid session."""
    try:
        path = getattr(request, "path", "") or ""
    except Exception:
        path = ""
    query = path.split("?", 1)[1] if "?" in path else ""
    token = ""
    session = ""
    for part in query.split("&"):
        if part.startswith("token="):
            token = part[len("token="):]
        elif part.startswith("session="):
            session = part[len("session="):]

    if token and hmac.compare_digest(token, _HTTP_TOKEN):
        return None
    if session and _valid_session(session):
        return None

    try:
        headers = getattr(request, "headers", None)
        if headers:
            cookie_hdr = headers.get("Cookie", "") or headers.get("cookie", "")
            if cookie_hdr:
                for chunk in cookie_hdr.split(";"):
                    chunk = chunk.strip()
                    if chunk.startswith("iris_session="):
                        c_sess = chunk[len("iris_session="):].strip()
                        if _valid_session(c_sess):
                            return None
            hdr_sess = headers.get("X-Iris-Session", "") or headers.get("X-Iris-Token", "")
            if hdr_sess and _valid_session(hdr_sess):
                return None
            if hdr_sess and hmac.compare_digest(hdr_sess, _HTTP_TOKEN):
                return None
    except Exception:
        pass

    try:
        peer = getattr(connection, "remote_address", None)
        peer = peer[0] if peer else ""
    except Exception:
        peer = ""
    if _is_loopback_address(peer):
        return None

    from websockets.datastructures import Headers
    from websockets.http11 import Response
    log.warning("WS connection rejected from %s (missing or invalid auth)", peer)
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
            if _app.cfg.get("lan_access", False):
                return "0.0.0.0"
        else:
            from config import load_config
            if load_config().get("lan_access", False):
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
    return "http://%s:15502" % host


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


_LOGIN_FAILURES = {}  # ip -> (count, lockout_until)


def _check_auth_rate_limit(ip):
    """Return (allowed: bool, retry_after: int)."""
    now = time.time()
    record = _LOGIN_FAILURES.get(ip)
    if not record:
        return True, 0
    count, lockout_until = record
    if now < lockout_until:
        return False, max(1, int(lockout_until - now))
    if count >= 5 and now >= lockout_until:
        _LOGIN_FAILURES.pop(ip, None)
        return True, 0
    return True, 0


def _record_auth_failure(ip):
    now = time.time()
    record = _LOGIN_FAILURES.get(ip, (0, 0))
    count = record[0] + 1
    lockout_until = record[1]
    if count >= 5:
        lockout_until = now + 60.0  # 60s lockout after 5 consecutive failures
    _LOGIN_FAILURES[ip] = (count, lockout_until)


def _record_auth_success(ip):
    _LOGIN_FAILURES.pop(ip, None)


def _is_authorized_slot(slot, cfg):
    """Verify that an action slot requested by a remote peer matches a pre-configured button."""
    if not isinstance(slot, dict) or not isinstance(cfg, dict):
        return False
    stype = str(slot.get("type") or "").strip()
    if not stype:
        return False

    # Safe built-in controls that only affect media transport or audio toggling
    if stype in ("MEDIA_PLAY", "MEDIA_NEXT", "MEDIA_PREV", "MEDIA_EJECT", "AUDIO OUTPUT", "EMPTY"):
        return True

    candidates = []
    candidates.extend(cfg.get("panel_board") or [])
    candidates.extend(cfg.get("panel_utility") or [])
    candidates.extend(cfg.get("panel_core") or [])
    for prof in cfg.get("panel_profiles") or []:
        if isinstance(prof, dict):
            candidates.extend(prof.get("board") or [])

    spath = str(slot.get("shortcut_path") or "").strip()
    sargs = str(slot.get("shortcut_args") or "").strip()
    saction = str(slot.get("core_action") or "").strip()
    sentity = str(slot.get("entity") or slot.get("entity_id") or "").strip()
    shotkey = str(slot.get("hotkey") or "").strip()
    sbtn = str(slot.get("button_id") or "").strip()
    sname = str(slot.get("name") or "").strip()

    for c in candidates:
        if not isinstance(c, dict):
            continue
        if str(c.get("type") or "").strip() != stype:
            continue
        if stype in ("SHORTCUT", "GROUP"):
            cpath = str(c.get("shortcut_path") or "").strip()
            cargs = str(c.get("shortcut_args") or "").strip()
            if cpath == spath and cargs == sargs:
                return True
        elif stype == "CORE":
            if str(c.get("core_action") or "").strip() == saction:
                return True
        elif stype == "MACRO":
            # Match on slot name or matching actions count
            if sname and str(c.get("name") or "").strip() == sname:
                return True
            if c.get("actions") and slot.get("actions") and len(c.get("actions")) == len(slot.get("actions")):
                return True
        elif stype in ("TOGGLE", "HOTKEY", "ACTION", "SENSOR"):
            centity = str(c.get("entity") or c.get("entity_id") or "").strip()
            cbtn = str(c.get("button_id") or "").strip()
            chotkey = str(c.get("hotkey") or "").strip()
            if (centity and centity == sentity) or (cbtn and cbtn == sbtn) or (chotkey and chotkey == shotkey):
                return True
            if sname and str(c.get("name") or "").strip() == sname:
                return True
    return False


class _RequestHandler(SimpleHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    extensions_map = SimpleHTTPRequestHandler.extensions_map.copy()
    extensions_map.update({
        ".woff2": "font/woff2",
        ".woff": "font/woff",
        ".ttf": "font/ttf",
        ".otf": "font/otf",
    })

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
                if origin and origin != "null":
                    from urllib.parse import urlparse
                    try:
                        op = urlparse(origin)
                        if op.hostname and op.hostname not in ("127.0.0.1", "localhost", "::1", "0.0.0.0"):
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
        "connect-src 'self' ws: wss: https://fonts.googleapis.com https://fonts.gstatic.com; "
        "media-src 'self'; "
        "frame-src 'self'; "
        "base-uri 'none'; "
        "form-action 'none'; "
        "frame-ancestors 'self'"
    )

    def end_headers(self):
        try:
            buf = getattr(self, "_headers_buffer", [])
            has_cc = any(b"cache-control:" in h.lower() for h in buf)
            if not has_cc:
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
        # Library images, media art, and CSS webfonts cannot carry custom Authorization headers,
        # so serve these with host-only validation.
        if self.path.startswith("/api/library/image/") or self.path.startswith("/api/mdi/font"):
            if not self._host_ok():
                self._reject_unauthorized()
                return
            if self.path.startswith("/api/mdi/font"):
                self._serve_mdi_font()
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
        elif self.path == "/api/audio/devices":
            self._handle_audio_devices()
        elif self.path == "/api/sounds":
            self._send_json(_get_sounds())
        elif self.path.startswith("/api/sounds/preview/"):
            self._handle_sound_preview(self.path.split("/")[-1])
        elif self.path == "/api/sounds/stop":
            self._handle_sound_stop()
        elif self.path == "/api/vision/sensors":
            self._send_json(_get_vision_sensors())
        elif self.path == "/api/automations":
            self._handle_get_automations()
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
        elif self.path == "/api/library/open_folder" or self.path.startswith("/api/library/open_folder?"):
            self._handle_library_open_folder()
        elif self.path == "/api/volume/master":
            self._send_json(_get_master_volume())
        elif self.path == "/api/volume":
            self._send_json(_get_volume())
        elif self.path == "/api/panel":
            self._send_json(_get_panel())
        elif self.path.startswith("/api/panel/live"):
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            client_cv = (qs.get("cv") or [""])[0] or None
            self._send_json(_get_panel_live(client_cv))
        elif self.path == "/api/kraken/detect":
            self._handle_kraken_detect()
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
        elif self.path == "/api/lighting/status":
            self._handle_lighting_status()
        elif self.path.startswith("/api/dialog/browse"):
            self._handle_dialog_browse()
        elif self.path.startswith("/api/notepad/open"):
            self._handle_notepad_open()
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
            self._serve_static_asset()

    def _serve_static_asset(self):
        """Serve a web asset either from local HTML/ (dev) or memory (embedded_assets)."""
        rel_path = self.path.split("?", 1)[0].lstrip("/")
        if not rel_path:
            rel_path = "index.html"

        # 1. If in dev mode and file exists on disk, let SimpleHTTPRequestHandler handle it
        if _USE_DEV_ASSETS and os.path.isfile(os.path.join(self.directory, rel_path)):
            super().do_GET()
            return

        # 2. Otherwise, serve from embedded assets
        if embedded_assets and embedded_assets.has_asset(rel_path):
            ae = self.headers.get("Accept-Encoding", "")
            prefer_gzip = "gzip" in ae.lower()

            res = embedded_assets.get_asset_bytes(rel_path, prefer_gzip=prefer_gzip)
            if res is None:
                self.send_error(404)
                return

            body, content_type, etag, is_gzipped = res

            # Check If-None-Match ETag header
            inm = self.headers.get("If-None-Match", "")
            if inm and inm.strip() == etag:
                self.send_response(304)
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("ETag", etag)

            # Long-term caching for static assets (service worker handles cache busting)
            if rel_path.endswith((".woff2", ".ttf", ".png", ".jpg", ".ico")):
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
            elif rel_path in ("script.js", "style.css", "settings_renderer.js", "sw.js"):
                self.send_header("Cache-Control", "no-cache")

            if is_gzipped:
                self.send_header("Content-Encoding", "gzip")

            self.end_headers()
            self.wfile.write(body)
            return

        # 3. Fall back to standard file handler or 404
        if os.path.isfile(os.path.join(self.directory, rel_path)):
            super().do_GET()
        else:
            self.send_error(404)

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
        elif self.path == "/api/plugins/open_folder":
            self._handle_plugins_open_folder()
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
        elif self.path == "/api/automations":
            self._handle_save_automation()
        elif self.path.startswith("/api/automations/") and self.path.endswith("/delete"):
            rule_id = self.path.split("/")[-2]
            self._handle_delete_automation(rule_id)
        elif self.path == "/api/automations/disclaimer_ack":
            self._handle_automations_disclaimer_ack()
        elif self.path == "/api/automations/test":
            self._handle_test_automation()
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
        elif self.path == "/api/panel/open_library":
            self._handle_panel_open_library()
        elif self.path == "/api/open_url":
            self._handle_open_url()
        elif self.path.startswith("/api/library/sidecar/"):
            self._handle_library_save_sidecar(self.path[len("/api/library/sidecar/"):])
        elif self.path == "/api/library/note":
            self._handle_library_save_note()
        elif self.path.startswith("/api/notepad/open"):
            self._handle_notepad_open()
        elif self.path == "/api/clipboard":
            self._handle_clipboard()
        elif self.path.startswith("/api/library/delete/"):
            self._handle_library_delete(self.path[len("/api/library/delete/"):])
        elif self.path == "/api/library/open_folder":
            self._handle_library_open_folder()
        else:
            self.send_error(404)

    def _handle_clipboard(self):
        """Native clipboard copy without browser permission prompts."""
        try:
            body = self._read_json()
            text = str(body.get("text", ""))
            if text:
                import win_platform
                win_platform.copy_to_clipboard(text)
            self._send_json({"ok": True})
        except Exception as ex:
            self._send_json({"ok": False, "error": str(ex)})

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
        _media_dir = os.path.join(_ROOT_DIR, "media")
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

        client_ip = getattr(self, "client_address", [None])[0] or "unknown"
        allowed, retry_after = _check_auth_rate_limit(client_ip)
        if not allowed:
            body = (f'{{"ok":false,"error":"rate_limited","retry_after":{retry_after}}}').encode("utf-8")
            self.send_response(429)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Retry-After", str(retry_after))
            self.end_headers()
            self.wfile.write(body)
            return

        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        token = ""
        for part in query.split("&"):
            if part.startswith("token="):
                token = part[len("token="):]
        if not isinstance(token, str) or not token or not hmac.compare_digest(token, _HTTP_TOKEN):
            _record_auth_failure(client_ip)
            body = b'{"ok":false,"error":"invalid access token"}'
            self.send_response(403)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        _record_auth_success(client_ip)
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

        client_ip = getattr(self, "client_address", [None])[0] or "unknown"
        allowed, retry_after = _check_auth_rate_limit(client_ip)
        if not allowed:
            self._send_json({
                "ok": False,
                "error": "rate_limited",
                "message": f"Too many failed attempts. Try again in {retry_after} seconds."
            }, status=429)
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
            _record_auth_failure(client_ip)
            self._send_json({"ok": False, "error": "incorrect_password"}, status=401)
            return

        _record_auth_success(client_ip)
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

    def _handle_kraken_detect(self):
        """Return Kraken LCD probe status from the rgb plugin or entity bus."""
        import plugin_manager
        inst = plugin_manager.get("rgb")
        if inst and hasattr(inst, "get_kraken_status"):
            data = inst.get_kraken_status()
        else:
            data = {"found": False}
        self._send_json(data)

    def _handle_save_panel_password(self):
        """Handle POST /api/panel/password to set or update the Argon2id hash."""
        if not self._is_loopback_peer():
            self._send_json({"ok": False, "error": "forbidden"})
            return

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

        html = None
        # 1. Dev mode: read from disk if available
        if _USE_DEV_ASSETS:
            index_path = os.path.join(self.directory, "index.html")
            if os.path.isfile(index_path):
                try:
                    with open(index_path, "rb") as f:
                        html = f.read()
                except Exception:
                    html = None

        # 2. Production / Embedded assets fallback
        if html is None and embedded_assets and embedded_assets.has_asset("index.html"):
            res = embedded_assets.get_asset_bytes("index.html", prefer_gzip=False)
            if res:
                html = res[0]

        if html is None:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def _serve_login(self):
        """Serve the pairing info page for unauthorized LAN peers."""
        html = None
        if _USE_DEV_ASSETS:
            login_path = os.path.join(self.directory, "login.html")
            if os.path.isfile(login_path):
                try:
                    with open(login_path, "rb") as f:
                        html = f.read()
                except Exception:
                    html = None

        if html is None and embedded_assets and embedded_assets.has_asset("login.html"):
            res = embedded_assets.get_asset_bytes("login.html", prefer_gzip=False)
            if res:
                html = res[0]

        if html is None:
            self.send_error(404)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(html)))
        self.end_headers()
        self.wfile.write(html)

    def _serve_apk(self):
        """Serve the compiled Android APK file with attachment headers."""
        data = None
        if _USE_DEV_ASSETS:
            apk_path = os.path.join(self.directory, "Iris.apk")
            if os.path.isfile(apk_path):
                try:
                    with open(apk_path, "rb") as f:
                        data = f.read()
                except Exception:
                    data = None

        if data is None and embedded_assets and embedded_assets.has_asset("Iris.apk"):
            res = embedded_assets.get_asset_bytes("Iris.apk", prefer_gzip=False)
            if res:
                data = res[0]

        if data is None:
            self.send_error(404, "Iris.apk not found")
            return

        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/vnd.android.package-archive")
            self.send_header("Content-Disposition", 'attachment; filename="Iris.apk"')
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
        body = json.dumps(data, separators=(',', ':')).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_portal_reload(self):
        try:
            broadcast({"type": "reload", "hard": True})
            if _app and getattr(_app, "_main_win", None):
                try:
                    _app._root.after_idle(_app._main_win.reload_theme)
                except Exception:
                    pass
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("[http] portal reload broadcast failed: %s", e)
            self.send_error(500, str(e))

    def _handle_save_config(self):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
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
            if "run_at_startup" in body:
                try:
                    from startup import set_startup
                    set_startup(bool(body["run_at_startup"]))
                except Exception as e:
                    log.warning("[http] failed to apply run_at_startup: %s", e)
            if "hotkey_overlay" in body or "hotkey_toolbar" in body or "hotkey_borderless" in body:
                if hasattr(_app, "_reregister_hotkey"):
                    try:
                        _app._reregister_hotkey()
                    except Exception as e:
                        log.warning("[http] failed to reregister hotkeys: %s", e)
            self._push_config_to_device(body)
            try:
                from lighting_service import get_lighting_service
                get_lighting_service().update_config(_app.cfg)
            except Exception as e:
                log.warning("[http] lighting config update failed: %s", e)
            broadcast({"type": "config", "config": body})
            if "theme" in body:
                broadcast({"type": "theme", "theme": body["theme"], "reload": True})
                if getattr(_app, "_main_win", None):
                    try:
                        _app._root.after_idle(_app._main_win.reload_theme)
                    except Exception:
                        pass
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

                    if "pc_stats_manual" in body or "pc_disp" in body:
                        manual = bool(body.get("pc_stats_manual", _app.cfg.get("pc_stats_manual", False)))
                        flags = body.get("pc_disp", _app.cfg.get("pc_disp", 7))
                        serial_sender.set_live("pc_disp", str(int(flags)) if manual else "0")
                except Exception as e:
                    log.warning("[http] device push failed: %s", e)

        threading.Thread(target=_send, daemon=True).start()

    def _handle_plugins_open_folder(self):
        """Open the user plugins folder in Explorer, creating it first if needed."""
        if not self._is_loopback_peer():
            self._send_json({"ok": False, "error": "forbidden"})
            return
        try:
            import plugin_manager
            folder = plugin_manager.user_plugins_dir()
            os.startfile(folder)
            self._send_json({"ok": True, "path": folder})
        except Exception as e:
            log.warning("[http] open plugins folder failed: %s", e)
            self.send_error(500, str(e))

    def _read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length > _MAX_BODY_SIZE:
            self.send_error(413, "Request entity too large")
            return {}
        if length:
            try:
                return json.loads(self.rfile.read(length))
            except Exception:
                self.send_error(400, "Invalid JSON body")
                return {}
        return {}

    def _handle_screenshot_latest(self):
        """Return the most recent screenshot captured by the Tk dialog."""
        if _app is None:
            self._send_json({"available": False, "seq": 0})
            return
        data = getattr(_app, "screenshot_last", None)
        if not data:
            self._send_json({"available": False, "seq": getattr(_app, "screenshot_seq", 0)})
            return
        self._send_json({"available": True, **data})

    def _handle_audio_devices(self):
        """Return active audio playback devices and current default."""
        try:
            from win_platform import get_audio_output_devices, get_current_default_audio_output
            devs = get_audio_output_devices()
            cur = get_current_default_audio_output()
            self._send_json({"ok": True, "devices": devs, "current": cur})
        except Exception as e:
            log.warning("[http] /api/audio/devices error: %s", e)
            self._send_json({"ok": False, "devices": [], "current": None})

    # ── Library ────────────────────────────────────────────────────────────

    def _screenshots_folder(self):
        cfg = getattr(_app, "cfg", None) if _app is not None else None
        return paths.get_screenshots_dir(cfg)

    def _notes_folder(self):
        cfg = getattr(_app, "cfg", None) if _app is not None else None
        return paths.get_notes_dir(cfg)

    def _library_folders(self):
        folders = []
        sf = self._screenshots_folder()
        nf = self._notes_folder()
        for f in (sf, nf):
            if f and f not in folders:
                folders.append(f)
        # Check legacy directory for backward-compatibility with existing files
        legacy = os.path.abspath(os.path.join(os.path.expanduser("~"), "Documents", "Iris", "Screenshots"))
        if os.path.isdir(legacy) and legacy not in folders:
            folders.append(legacy)
        return folders

    def _find_library_file(self, filename):
        fname = os.path.basename(filename)
        for folder in self._library_folders():
            cand = os.path.join(folder, fname)
            if os.path.isfile(cand):
                return folder, cand
        # Default destination if not found
        if fname.lower().endswith(".txt"):
            return self._notes_folder(), os.path.join(self._notes_folder(), fname)
        return self._screenshots_folder(), os.path.join(self._screenshots_folder(), fname)

    def _library_folder(self):
        """Legacy helper returning screenshots folder."""
        return self._screenshots_folder()

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
        """List all screenshots and notes across the library folders."""
        items = []
        seen = set()
        try:
            for folder in self._library_folders():
                if not os.path.isdir(folder):
                    continue
                all_files = os.listdir(folder)
                for fname in all_files:
                    if fname in seen:
                        continue
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
                            seen.add(fname)
                            items.append({
                                "type": "screenshot",
                                "filename": fname,
                                "app": "orphan",
                                "ts": ts,
                                "title": title,
                            })
                        continue

                    seen.add(fname)
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
                        title = ""
                        preview = ""
                        fpath = os.path.join(folder, fname)
                        try:
                            with open(fpath, encoding="utf-8") as f:
                                content = f.read(500)
                            lines = content.split("\n")
                            body_lines = []
                            for idx, line in enumerate(lines):
                                if idx == 0 and line.startswith("title:"):
                                    title = line[6:].strip()
                                else:
                                    clean_line = re.sub(r"<[^>]+>", " ", line)
                                    clean_line = clean_line.replace("&nbsp;", " ").strip()
                                    if clean_line:
                                        body_lines.append(clean_line)
                            preview = body_lines[0][:80] if body_lines else ""
                        except Exception:
                            pass
                        items.append({
                            "type": "note",
                            "filename": fname,
                            "app": meta["app"],
                            "ts": ts,
                            "title": title,
                            "preview": preview,
                        })

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
        folder, path = self._find_library_file(filename)
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
        folder, _ = self._find_library_file(filename)
        sc_path = self._sidecar_path(folder, filename)
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
        folder, img_path = self._find_library_file(filename)
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
            if "title" in body:
                existing["title"] = str(body["title"])
            if "annotations" in body and isinstance(body["annotations"], list):
                existing["annotations"] = body["annotations"]
            with open(sc_path, "w", encoding="utf-8") as f:
                json.dump(existing, f, ensure_ascii=False)
            broadcast({"type": "library_update"})
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("library sidecar save error: %s", e)
            self.send_error(500)

    def _handle_library_get_note(self, filename):
        """Return the content of a note file."""
        filename = os.path.basename(filename)
        folder, path = self._find_library_file(filename)
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
            raw_filename = str(body.get("filename", "")).strip()

            folder = self._notes_folder()
            os.makedirs(folder, exist_ok=True)

            if not raw_filename:
                ts = _t.strftime("%Y%m%d_%H%M%S")
                filename = "iris_note_%s_%s.txt" % (app, ts)
            else:
                base = os.path.basename(raw_filename)
                # Strip extension and sanitize base name
                if base.lower().endswith(".txt"):
                    base = base[:-4]
                base = _re.sub(r'[^a-zA-Z0-9_\-\. ]+', '_', base).strip('._ ')
                if not base:
                    base = f"note_{int(_t.time())}"
                filename = f"{base}.txt"

            path = os.path.join(folder, filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write("title:%s\n%s" % (title, content))
            broadcast({"type": "library_update"})
            self._send_json({"ok": True, "filename": os.path.basename(path)})
        except Exception as e:
            log.warning("library note save error: %s", e)
            self.send_error(500)

    def _handle_library_delete(self, filename):
        """Delete a library item (PNG + sidecar, or note txt)."""
        if not self._is_loopback_peer():
            self._send_json({"ok": False, "error": "forbidden"})
            return
        filename = os.path.basename(filename)
        folder, path = self._find_library_file(filename)
        try:
            if not os.path.isfile(path):
                self.send_error(404)
                return
            os.remove(path)
            # Also remove sidecar if it's a PNG
            if filename.lower().endswith(".png"):
                sc = self._sidecar_path(folder, filename)
                if os.path.isfile(sc):
                    os.remove(sc)
            broadcast({"type": "library_update"})
            self._send_json({"ok": True})
        except Exception as e:
            log.warning("library delete error: %s", e)
            self.send_error(500)

    def _handle_library_open_folder(self):
        """Open the screenshots library folder in Explorer, optionally selecting a specific file."""
        if not self._is_loopback_peer():
            self._send_json({"ok": False, "error": "forbidden"})
            return
        try:
            fname = None
            if self.command == "POST":
                body = self._read_json()
                fname = body.get("filename") if isinstance(body, dict) else None
            elif "?" in self.path:
                from urllib.parse import parse_qs, urlparse
                qs = parse_qs(urlparse(self.path).query)
                files = qs.get("file") or qs.get("filename")
                if files:
                    fname = files[0]

            folder = self._screenshots_folder()
            if not os.path.isdir(folder):
                os.makedirs(folder, exist_ok=True)
            if fname:
                _, full_path = self._find_library_file(fname)
                if full_path and os.path.isfile(full_path):
                    import subprocess
                    norm_path = os.path.normpath(full_path)
                    subprocess.Popen(["explorer.exe", f"/select,{norm_path}"], shell=False)
                    self._send_json({"ok": True, "path": norm_path})
                    return
            os.startfile(folder)
            self._send_json({"ok": True, "path": folder})
        except Exception as e:
            log.warning("library open folder error: %s", e)
            self.send_error(500, str(e))

    def _handle_library_running_apps(self):
        """Return a list of currently running process names for the note app picker."""
        try:
            from win_platform import get_running_process_names
            names = get_running_process_names(ttl=1.0)
            seen = set()
            apps = []
            import re as _re
            for name in names:
                try:
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

        ocr_res = {}
        try:
            img = vision.capture(bbox)
            ocr_res = vision.ocr_extract(img)
        except Exception:
            pass

        self._send_json({
            "exe": exe,
            "anchor": anchor,
            "region": region,
            "screenshot_b64": img_b64,
            "detected_text": ocr_res.get("text", ""),
            "words": ocr_res.get("words", []),
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
            "value": result.get("value", 0.0),
            "text": result.get("text", ""),
            "active": result.get("active", False),
            "mode": result.get("mode", ""),
            "words": result.get("words", []),
        })

    def _handle_vision_create_sensor(self):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
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
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
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
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
        sensors = _vision_sensors()
        before = len(sensors)
        _vision_sensors()[:] = [s for s in sensors if s.get("id") != sensor_id]
        _save_vision_config()
        self._send_json({"ok": len(_vision_sensors()) < before})

    # ── Automations API Handlers ───────────────────────────────────

    def _handle_get_automations(self):
        import automations
        engine = automations.get_engine()
        self._send_json({
            "ok": True,
            "rules": engine.get_rules(),
            "disclaimer_acknowledged": engine.is_disclaimer_acknowledged(),
        })

    def _handle_save_automation(self):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        if _app is None:
            self.send_error(503, "App not registered")
            return
        import automations
        engine = automations.get_engine()
        rules = engine.get_rules()

        rule = dict(body or {})
        rule_id = rule.get("id")
        if not rule_id:
            rule_id = f"auto_{int(time.time())}_{len(rules)+1}"
            rule["id"] = rule_id

        idx = next((i for i, r in enumerate(rules) if r.get("id") == rule_id), None)
        if idx is not None:
            rules[idx] = rule
        else:
            rules.append(rule)

        engine.save_rules(rules, _app.cfg)
        self._send_json({"ok": True, "rule": rule})

    def _handle_delete_automation(self, rule_id):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
        if _app is None:
            self.send_error(503, "App not registered")
            return
        import automations
        engine = automations.get_engine()
        rules = [r for r in engine.get_rules() if r.get("id") != rule_id]
        engine.save_rules(rules, _app.cfg)
        self._send_json({"ok": True})

    def _handle_automations_disclaimer_ack(self):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
        if _app is None:
            self.send_error(503, "App not registered")
            return
        import automations
        engine = automations.get_engine()
        engine.set_disclaimer_ack(True)
        _app.cfg["automations_disclaimer_ack"] = True
        try:
            from config import save_config
            save_config(_app.cfg)
        except Exception:
            pass
        self._send_json({"ok": True, "disclaimer_acknowledged": True})

    def _handle_test_automation(self):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        import automations
        engine = automations.get_engine()
        engine._execute_actions(body, "TEST_TRIGGER")
        self._send_json({"ok": True})

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
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
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
            log.info("[panel_save] broadcasting config to %d WS client(s)", len(CLIENTS))
            broadcast({
                "type": "config",
                "config": {
                    "panel_board": _app.cfg.get("panel_board", []),
                    "panel_utility": _app.cfg.get("panel_utility", []),
                    "panel_core": _app.cfg.get("panel_core", []),
                    "panel_sliders": _app.cfg.get("panel_sliders", []),
                    "panel_layout": _app.cfg.get("panel_layout", []),
                    "panel_gauges": _app.cfg.get("panel_gauges", {}),
                    "panel_profiles": _app.cfg.get("panel_profiles", []),
                    "media_player_path": _app.cfg.get("media_player_path", ""),
                }
            })
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
            is_url = p.startswith(("http://", "https://")) or (("." in p) and ("/" in p or "\\" not in p) and not os.path.isabs(p) and not p.lower().endswith((".exe", ".lnk", ".bat", ".cmd", ".vbs", ".ps1")))
            if not is_url:
                p = os.path.expandvars(os.path.expanduser(p))
                if not os.path.isfile(p):
                    which_p = shutil.which(p)
                    if which_p and os.path.isfile(which_p):
                        p = which_p
                    else:
                        base_dir = _ROOT_DIR
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
            norm = p.lower() if is_url else os.path.normcase(os.path.abspath(p))
            with _APP_ICON_LOCK:
                cached = _APP_ICON_CACHE.get(norm)
                if cached is not None:
                    _APP_ICON_CACHE.move_to_end(norm)

            if cached is None:
                with _APP_ICON_LOCK:
                    # Double-check after lock
                    cached = _APP_ICON_CACHE.get(norm)
                    if cached is not None:
                        _APP_ICON_CACHE.move_to_end(norm)
                    else:
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
                        if len(_APP_ICON_CACHE) >= 200:
                            _APP_ICON_CACHE.popitem(last=False)
                        _APP_ICON_CACHE[norm] = (blob, color)
                        cached = (blob, color)

            blob, color = cached
            etag = f'"{abs(hash(norm + str(len(blob))))}"'
            inm = self.headers.get("If-None-Match", "").strip()
            if inm and inm == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "public, max-age=86400")
                self.end_headers()
                return

            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(blob)))
            self.send_header("Cache-Control", "public, max-age=86400")
            self.send_header("ETag", etag)
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
            is_url = p.startswith(("http://", "https://")) or (("." in p) and ("/" in p or "\\" not in p) and not os.path.isabs(p) and not p.lower().endswith((".exe", ".lnk", ".bat", ".cmd", ".vbs", ".ps1")))
            if not is_url:
                p = os.path.expandvars(os.path.expanduser(p))
                if not os.path.isfile(p):
                    which_p = shutil.which(p)
                    if which_p and os.path.isfile(which_p):
                        p = which_p
                    else:
                        base_dir = _ROOT_DIR
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
            norm = p.lower() if is_url else os.path.normcase(os.path.abspath(p))
            with _APP_ICON_LOCK:
                cached = _APP_ICON_CACHE.get(norm)
                if cached is not None:
                    _APP_ICON_CACHE.move_to_end(norm)
            if cached is not None:
                _, color = cached
            else:
                with _APP_ICON_LOCK:
                    cached = _APP_ICON_CACHE.get(norm)
                    if cached is not None:
                        _APP_ICON_CACHE.move_to_end(norm)
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
                        if len(_APP_ICON_CACHE) >= 200:
                            _APP_ICON_CACHE.popitem(last=False)
                        _APP_ICON_CACHE[norm] = (blob, color)
            self._send_json({"ok": True, "path": p, "color": color})
        except Exception as e:
            log.warning("[http] icon meta extraction failed: %s", e)
            self._send_json({"ok": False, "error": str(e)})

    def _serve_mdi_font(self):
        """Serve the MDI webfont so the web panel renders the same icons as Tk."""
        try:
            import mdi_icons
            path = str(mdi_icons.FONT_PATH)
        except Exception:
            path = ""
        if not path or not os.path.isfile(path):
            path = os.path.join(_HTML_DIR, "mdi-webfont.ttf")
        if not os.path.isfile(path):
            path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "mdi-webfont.ttf")
        if not os.path.isfile(path) and embedded_assets and embedded_assets.has_asset("mdi-webfont.ttf"):
            res = embedded_assets.get_asset_bytes("mdi-webfont.ttf", prefer_gzip=False)
            if res:
                data = res[0]
                self.send_response(200)
                self.send_header("Content-Type", "font/ttf")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Cache-Control", "public, max-age=31536000, immutable")
                self.end_headers()
                self.wfile.write(data)
                return

        if not os.path.isfile(path):
            self.send_error(404)
            return
        try:
            with open(path, "rb") as f:
                data = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "font/ttf")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Cache-Control", "public, max-age=31536000, immutable")
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

    def _handle_notepad_open(self):
        from urllib.parse import urlparse, parse_qs
        qs = parse_qs(urlparse(self.path).query)
        filename = (qs.get("file") or [None])[0]
        app_tag = (qs.get("app") or ["general"])[0]
        initial_title = (qs.get("title") or [None])[0]
        initial_body = (qs.get("body") or [None])[0]
        if self.command == "POST":
            try:
                body = self._read_json()
                if body:
                    filename = body.get("file") or body.get("filename") or filename
                    app_tag = body.get("app") or app_tag
                    initial_title = body.get("title") or initial_title
                    initial_body = body.get("body") or initial_body
            except Exception:
                pass
        toggle = self._get_query_param("toggle") in ("1", "true", "yes")
        try:
            import notepad_window
            notepad_window.open_notepad(app_tag=app_tag, filename=filename, initial_title=initial_title, initial_body=initial_body, toggle=toggle)
            self._send_json({"ok": True})
        except Exception as ex:
            log.warning("[http] failed to open notepad window: %s", ex)
            self._send_json({"ok": False, "error": str(ex)})

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

        if art_id:
            etag = f'"{art_id}"'
            inm = self.headers.get("If-None-Match", "").strip()
            if inm and inm == etag:
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "public, max-age=60")
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
        if not self._is_loopback_peer():
            self._send_json({"ok": False, "path": "", "error": "forbidden"})
            return
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
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
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

    def _handle_panel_open_library(self):
        """Open the Iris settings app directly on the Library > Notes tab (same as toolbar Library button)."""
        try:
            import panel_window
            panel_window.open_panel(page="library", tab="notes")
            self._send_json({"ok": True})
        except Exception as ex:
            log.warning("[http] open library failed: %s", ex)
            self.send_error(500, str(ex))

    def _handle_panel_action(self):
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        slot = body.get("slot")
        if not self._is_loopback_peer():
            cfg = _app.cfg if _app is not None else {}
            if not _is_authorized_slot(slot, cfg):
                log.warning("[http] rejected unauthorized slot execution from remote peer: %s", slot)
                self.send_error(403, "Slot not authorized for remote execution")
                return
        try:
            from panel_runtime import execute_slot
            self._send_json(execute_slot(slot))
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
        elif tile in ("mic", "mic_mute"):
            try:
                from win_platform import toggle_mic_mute
                st = toggle_mic_mute()
            except Exception as e:
                log.warning("[http] mic toggle failed: %s", e)
                st = None
            self._send_json({"ok": st is not None, "state": st})
        elif tile in ("lighting_sync", "lighting"):
            try:
                st = _app._toggle_lighting_sync()
            except Exception as e:
                log.warning("[http] lighting sync toggle failed: %s", e)
                st = False
            self._send_json({"ok": True, "state": st})
        elif tile == "settings":
            try:
                if hasattr(_app, "_open_settings"):
                    _app._open_settings()
                else:
                    import panel_window
                    panel_window.open_panel()
            except Exception as e:
                log.warning("[http] settings open failed: %s", e)
            self._send_json({"ok": True})
        elif tile == "toolbar":
            try:
                if hasattr(_app, "_toggle_capture_toolbar"):
                    _app._root.after(0, _app._toggle_capture_toolbar)
            except Exception as e:
                log.warning("[http] toolbar toggle failed: %s", e)
            self._send_json({"ok": True})
        elif tile == "colour_picker":
            try:
                mw = _app._ensure_main_win() if hasattr(_app, "_ensure_main_win") else getattr(_app, "_main_win", None)
                if mw:
                    _app._root.after(0, mw.start_colour_picker)
            except Exception as e:
                log.warning("[http] colour picker failed: %s", e)
            self._send_json({"ok": True})
        elif tile in ("screenshot", "screenshot_full"):
            try:
                mw = _app._ensure_main_win() if hasattr(_app, "_ensure_main_win") else getattr(_app, "_main_win", None)
                if mw:
                    _app._root.after(0, lambda: mw.start_screenshot({}, mode="fullscreen"))
            except Exception as e:
                log.warning("[http] screenshot failed: %s", e)
            self._send_json({"ok": True})
        elif tile == "screenshot_zone":
            try:
                mw = _app._ensure_main_win() if hasattr(_app, "_ensure_main_win") else getattr(_app, "_main_win", None)
                if mw:
                    _app._root.after(0, lambda: mw.start_screenshot({}, mode="zone"))
            except Exception as e:
                log.warning("[http] screenshot zone failed: %s", e)
            self._send_json({"ok": True})
        elif tile in ("note", "note_native", "note_webview"):
            try:
                mw = _app._ensure_main_win() if hasattr(_app, "_ensure_main_win") else getattr(_app, "_main_win", None)
                if mw:
                    _app._root.after(0, lambda: mw.start_quick_note(toggle=True))
            except Exception as e:
                log.warning("[http] quick note failed: %s", e)
            self._send_json({"ok": True})
        elif tile == "borderless_toggle":
            try:
                from win_platform import toggle_borderless_window
                st = toggle_borderless_window()
                self._send_json({"ok": True, "borderless": st})
            except Exception as e:
                log.warning("[http] borderless toggle failed: %s", e)
                self._send_json({"ok": False, "error": str(e)})
        elif tile == "stopwatch":
            try:
                if hasattr(_app, "_toggle_stopwatch"):
                    _app._root.after(0, _app._toggle_stopwatch)
            except Exception as e:
                log.warning("[http] stopwatch toggle failed: %s", e)
            self._send_json({"ok": True})
        elif tile == "countdown":
            try:
                if hasattr(_app, "_toggle_countdown"):
                    _app._root.after(0, _app._toggle_countdown)
            except Exception as e:
                log.warning("[http] countdown toggle failed: %s", e)
            self._send_json({"ok": True})
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

        # Prevent plugin presets from overwriting the user's default main board
        if not profile_id or profile_id == "__default__":
            profile_id = "__new__"

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
                prof["board"] = slots
            else:
                board = list(prof.get("board") or [])
                if slot_idx is not None and int(slot_idx) >= 0:
                    while len(board) <= int(slot_idx):
                        board.append({"type": "EMPTY", "name": "", "icon": "border-none-variant", "color": ""})
                    if slots:
                        board[int(slot_idx)] = slots[0]
                else:
                    placed = False
                    for i in range(len(board)):
                        if board[i].get("type") == "EMPTY" and slots:
                            board[i] = slots[0]
                            placed = True
                            break
                    if not placed and slots:
                        board.append(slots[0])
                prof["board"] = sanitize_board(board)

            cfg["panel_profiles"] = sanitize_profiles(profiles)

        save_config(cfg)
        from panel_actions import _RESOLVE_CACHE
        _RESOLVE_CACHE["ts"] = 0.0
        _RESOLVE_CACHE["board"] = None

        self._send_json({"ok": True, "target_profile": target_name, "profile_id": profile_id, "count": len(slots)})

    def _handle_lighting_status(self):
        try:
            from lighting_service import get_lighting_service
            ls = get_lighting_service()
            self._send_json({
                "ok": True,
                "is_daytime": ls.is_daytime(),
                "providers": ls.get_providers()
            })
        except Exception as e:
            log.warning("[http] lighting status failed: %s", e)
            self._send_json({"ok": False, "providers": []})

    def _handle_panel_entities(self):
        try:
            from panel_entities import get_entity_registry, get_live_entity_states
            entities = get_entity_registry()
            live = {}
            try:
                live_raw = get_live_entity_states()
                for k, v in live_raw.items():
                    if isinstance(v, dict) and "value" in v:
                        live[k] = v.get("value")
                    else:
                        live[k] = v
            except Exception:
                pass
            self._send_json({"ok": True, "entities": entities, "live_states": live})
        except Exception as e:
            log.warning("[http] panel entities failed: %s", e)
            self._send_json({"ok": False, "entities": [], "live_states": {}})

    def _handle_save_plugin_config(self, name):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        if name == "matrix_display":
            if _app and isinstance(body, dict):
                from config import save_config
                if "brightness" in body:
                    try:
                        _app._set_brightness(max(0, min(4, int(body["brightness"]))))
                    except Exception:
                        pass
                _app.cfg.update(body)
                save_config(_app.cfg)
                self._push_config_to_device(body)
                broadcast({"type": "config", "config": body})
            self._send_json({"ok": True})
            return
        import plugin_manager
        if name == "vision":
            body = _merge_vision_config(body)
        pcfg = plugin_manager.get_plugin_config(name)
        if isinstance(body, dict):
            pcfg.update(body)
        plugin_manager.set_plugin_config(name, pcfg)
        # Trigger immediate check so exe/enabled changes take effect
        plugin_manager.check_plugins()
        self._send_json({"ok": True})

    def _handle_save_plugin_outputs(self, name):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        import plugin_manager
        if isinstance(body, dict):
            plugin_manager.set_plugin_outputs(name, body)
        self._send_json({"ok": True})

    def _handle_plugin_action(self, name, action_id):
        try:
            body = self._read_json() if self.command == "POST" else {}
        except Exception:
            body = {}
        import plugin_manager
        inst = plugin_manager.get(name)
        if inst and hasattr(inst, "handle_action"):
            try:
                res = inst.handle_action(action_id, body)
                self._send_json({"ok": True, "result": res})
                return
            except Exception as e:
                log.warning("[http] plugin action %s.%s error: %s", name, action_id, e)
                self._send_json({"ok": False, "error": str(e)})
                return
        self._send_json({"ok": False, "error": "Plugin does not handle actions"})

    def log_message(self, fmt, *args):
        # suppress per-request logs
        pass


def _get_plugin_state():
    import plugin_manager
    try:
        plugin_manager.sync_plugin_themes()
    except Exception:
        pass
    result = {}
    for name, inst in list(plugin_manager._instances.items()):
        try:
            if hasattr(inst, "poll"):
                result[name] = inst.poll()
            else:
                result[name] = {"available": False}
        except Exception:
            result[name] = {"available": False}
    return result

def _get_plugin_snapshot(name):
    if name == "matrix_display":
        try:
            from serial_comm import serial_sender
            port = serial_sender.connected_port()
        except Exception:
            port = None
        if not port and _app:
            port = getattr(_app, "_port", None)
        is_conn = (port is not None) or bool(_app and getattr(_app, "_online", False))
        return {
            "available": is_conn,
            "connected": is_conn,
            "port": port or "—",
            "state": {"port": port or "—", "connected": is_conn},
            "status": {
                "port": port or "—",
                "connected": is_conn,
                "status_label": f"Connected ({port})" if (is_conn and port) else ("Connected" if is_conn else "Offline"),
                "message": f"Port: {port}" if (is_conn and port) else ("Connected" if is_conn else "Display disconnected"),
            },
        }
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
        
        # Resolve dynamic options for settings controls
        settings = manifest.get("settings", [])
        inst = plugin_manager.get(name)
        if inst:
            for section in settings:
                for ctrl in section.get("controls", []):
                    options_key = ctrl.get("options_key")
                    if options_key and hasattr(inst, "get_options"):
                        try:
                            opts = inst.get_options(options_key)
                            if opts:
                                ctrl["options"] = [{"value": o, "label": o} for o in opts]
                        except Exception as e:
                            log.debug(f"[ws_bridge] Failed to resolve options for {name}.{ctrl.get('key')}: {e}")
        
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
            "settings": settings,
            "config": dict(pcfg),
            "capabilities": capabilities,
            "status_fields": manifest.get("status", []),
            "outputs_def": manifest.get("outputs", []),
            "outputs": plugin_manager.get_plugin_outputs(name),
            "live_data_def": manifest.get("live_data", {}),
            "buttons_def": (inst.get_buttons_def() if (inst and hasattr(inst, "get_buttons_def")) else manifest.get("buttons", [])),
            "preset_layout": manifest.get("preset_layout", []),
            "panel_profiles": list(_app.cfg.get("panel_profiles") or []) if _app else [],
            "actions_def": manifest.get("actions", []),
            "diagnostics_def": manifest.get("diagnostics", []),
            "labels": manifest.get("labels", {}),
            "theme": manifest.get("theme"),
            "log_path": pcfg.get("log_path", ""),
            "is_hardware": plugin_manager.is_hardware_plugin(name, manifest),
        }

    # Core Matrix Display Hardware Plugin
    try:
        from serial_comm import serial_sender
        port = serial_sender.connected_port()
    except Exception:
        port = None
    if not port and _app:
        port = getattr(_app, "_port", None)
    is_matrix_online = (port is not None) or bool(_app and getattr(_app, "_online", False))
    matrix_status_code = "active" if is_matrix_online else "inactive"
    matrix_status_label = f"Connected ({port})" if (is_matrix_online and port) else ("Connected" if is_matrix_online else "Offline")
    matrix_cfg = dict(_app.cfg) if _app and hasattr(_app, "cfg") else {}
    try:
        matrix_cfg["pc_disp"] = int(matrix_cfg.get("pc_disp", 7))
    except Exception:
        matrix_cfg["pc_disp"] = 7
    matrix_settings = [
        {
            "title": "Clock Display",
            "controls": [
                {
                    "type": "select",
                    "key": "clock_mode",
                    "label": "Clock Mode",
                    "value_from": "_clock_mode",
                    "description": "Which clock style the matrix display shows.",
                    "options": [
                        {"value": "small", "label": "Small Clock"},
                        {"value": "large", "label": "Large Clock", "set": {"feature_large_clock": True, "feature_day_clock": False}},
                        {"value": "day", "label": "Day and time", "set": {"feature_large_clock": False, "feature_day_clock": True}}
                    ]
                },
                {
                    "type": "toggle",
                    "key": "feature_time",
                    "label": "Time display",
                    "description": "Show/hide current time on the matrix display."
                },
                {
                    "type": "toggle",
                    "key": "feature_date",
                    "label": "Date reminder",
                    "description": "Alternate time display with the current date."
                },
                {
                    "type": "toggle",
                    "key": "feature_minute_bar",
                    "label": "Minute bar",
                    "description": "Visual minute progress bar on display."
                },
                {
                    "type": "toggle",
                    "key": "feature_greeting",
                    "label": "Greeting message",
                    "description": "Show greeting message on startup."
                }
            ]
        },
        {
            "title": "Display Brightness",
            "controls": [
                {
                    "type": "slider",
                    "key": "brightness",
                    "label": "Display Brightness",
                    "min": 0,
                    "max": 4,
                    "step": 1,
                    "unit": "",
                    "description": "Brightness of the matrix display (0 = off, 4 = max)."
                }
            ]
        },
        {
            "title": "Display Features & Extras",
            "controls": [
                {
                    "type": "toggle",
                    "key": "feature_eyes",
                    "label": "Animated eyes",
                    "description": "Animated eyes that follow motion."
                },
                {
                    "type": "toggle",
                    "key": "night_mode_enabled",
                    "label": "Night mode",
                    "description": "Dim display during nighttime hours."
                },
                {
                    "type": "toggle",
                    "key": "feature_notifications",
                    "label": "Notifications",
                    "description": "Show phone and PC notifications on the matrix display."
                }
            ]
        },
        {
            "title": "PC Stats Display",
            "controls": [
                {
                    "type": "toggle",
                    "key": "pc_stats_enabled",
                    "label": "Automatic game detection",
                    "description": "Show CPU/GPU/FPS automatically when a detected game is running or a temperature alert fires."
                },
                {
                    "type": "toggle",
                    "key": "pc_stats_manual",
                    "label": "Persistent stats display",
                    "description": "Override the clock and keep PC stats on the matrix display permanently."
                },
                {
                    "type": "select",
                    "key": "pc_disp",
                    "label": "Number of stats",
                    "value_from": "pc_disp",
                    "description": "How many stats to show on the matrix display.",
                    "options": [
                        { "value": 1, "label": "1 stat (CPU)" },
                        { "value": 3, "label": "2 stats (CPU + GPU)" },
                        { "value": 7, "label": "3 stats (CPU + GPU + FPS)" }
                    ]
                }
            ]
        }
    ]

    result["matrix_display"] = {
        "display_name": "Matrix Display",
        "description": "Physical 32x8 LED pixel matrix display connected via USB serial.",
        "icon": "developer_board",
        "type": "hardware",
        "is_hardware": True,
        "is_core": True,
        "exe_path": "",
        "exe_default": "",
        "enabled": True,
        "running": is_matrix_online,
        "status_code": matrix_status_code,
        "status_label": matrix_status_label,
        "message": f"Port: {port}" if is_matrix_online else "Display disconnected",
        "requirements": [],
        "settings": matrix_settings,
        "config": matrix_cfg,
        "capabilities": {
            "status": True,
            "configuration": True,
            "outputs": False,
            "live_data": False,
            "actions": False,
            "diagnostics": False,
            "hardware": True
        },
        "status_fields": [
            {"key": "status_label", "label": "Connection", "source": "lifecycle"},
            {"key": "message", "label": "Port Details", "source": "lifecycle"}
        ],
        "outputs_def": [],
        "outputs": {},
        "live_data_def": {},
        "buttons_def": [],
        "preset_layout": [],
        "panel_profiles": [],
        "actions_def": [],
        "diagnostics_def": [],
        "labels": {
            "status": "HARDWARE CONNECTION",
            "configuration": "DISPLAY & CLOCK SETTINGS"
        },
        "theme": None,
        "log_path": "",
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
    media_dir = os.path.join(_ROOT_DIR, "media")
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
    import paths as _paths
    candidates = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings_pages.json"),
        os.path.join(str(Path(__file__).parent), "settings_pages.json"),
    ]
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        # One-file bundle: data is extracted next to the app package.
        candidates.append(os.path.join(meipass, "app", "settings_pages.json"))
        candidates.append(os.path.join(meipass, "settings_pages.json"))
    candidates.append(os.path.join(_paths.get_root_dir(), "app", "settings_pages.json"))
    for pages_path in candidates:
        try:
            if os.path.isfile(pages_path):
                with open(pages_path) as f:
                    data = json.load(f)
                if isinstance(data, dict) and "pages" in data:
                    return data
        except Exception as ex:
            log.warning("[settings] failed to load %s: %s", pages_path, ex)
    log.warning("[settings] settings_pages.json not found in any candidate location; settings UI will be empty")
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


def _get_panel_live(client_cv=None):
    from panel_runtime import live_payload
    if _app is None:
        return live_payload({}, client_cv=client_cv)
    return live_payload(_app.cfg, client_cv=client_cv)



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


class _QuietThreadingHTTPServer(ThreadingHTTPServer):
    """ThreadingHTTPServer that silently suppresses normal client disconnect errors."""

    def handle_error(self, request, client_address):
        ex = sys.exception() if hasattr(sys, "exception") else sys.exc_info()[1]
        if isinstance(ex, (ConnectionResetError, ConnectionAbortedError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)


def start_http(port=15502):
    os.makedirs(_HTML_DIR, exist_ok=True)
    host = _bind_host()
    handler = partial(_RequestHandler, directory=_HTML_DIR)
    server = _QuietThreadingHTTPServer((host, port), handler)
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
