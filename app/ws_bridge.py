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
from server.devices import (
    _DEVICE_TTL,
    _DEVICES,
    devices_path as _devices_path,
    load_devices as _load_devices,
    save_devices as _save_devices,
    touch_device as _touch_device,
    ua_device_name as _ua_device_name,
    get_devices as _get_devices,
    token_hash as _token_hash,
)

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


# ── Auth & Network helpers (modularized under server/) ─────────
from server.auth import (
    is_loopback_address as _is_loopback_address,
    valid_session as _valid_session,
    check_auth_rate_limit as _check_auth_rate_limit,
    record_auth_failure as _record_auth_failure,
    record_auth_success as _record_auth_success,
    is_authorized_slot as _is_authorized_slot,
)
from server.network import (
    lan_ip as _lan_ip,
    lan_url as _srv_lan_url,
    lan_pair_url as _srv_lan_pair_url,
    qr_bytes as _srv_qr_bytes,
)


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

    try:
        if _app is not None and _app.cfg.get("lan_access", True):
            return None
    except Exception:
        pass

    from websockets.datastructures import Headers
    from websockets.http11 import Response
    log.warning("WS connection rejected from %s (missing or invalid auth)", peer)
    return Response(401, "Unauthorized", Headers(), b"unauthorized")


async def _serve_ws(port):
    host = _bind_host()
    try:
        async with websockets.serve(
                handler, host, port, process_request=_ws_process_request):
            log.info("WS bridge listening on %s:%d", host, port)
            await asyncio.Future()
    except OSError as e:
        if getattr(e, "winerror", None) == 10048 or getattr(e, "errno", None) == 10048:
            log.warning("WS bridge port %d is already in use (another instance may be running).", port)
            return
        raise


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


def _lan_url():
    """Panel URL a LAN device can open (token is injected server-side)."""
    return _srv_lan_url(is_loopback=_is_loopback_mode())


def _lan_pair_url():
    """Pairing URL encoded in the on-screen QR code."""
    return _srv_lan_pair_url(_HTTP_TOKEN, is_loopback=_is_loopback_mode())


def _qr_bytes():
    """Render the one-time pairing URL as a QR code PNG."""
    return _srv_qr_bytes(_lan_pair_url())


from server.audio import AudioHandlerMixin
from server.automations import AutomationsHandlerMixin
from server.library import LibraryHandlerMixin
from server.notifications import NotificationsHandlerMixin
from server.panel import PanelHandlerMixin
from server.plugins import PluginsHandlerMixin
from server.system import SystemHandlerMixin
from server.vision import (
    VisionHandlerMixin,
    vision_sensors as _vision_sensors,
    save_vision_config as _save_vision_config,
    normalize_sensor as _normalize_sensor,
)


class _RequestHandler(
    AudioHandlerMixin,
    AutomationsHandlerMixin,
    LibraryHandlerMixin,
    NotificationsHandlerMixin,
    PanelHandlerMixin,
    PluginsHandlerMixin,
    SystemHandlerMixin,
    VisionHandlerMixin,
    SimpleHTTPRequestHandler,
):
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
        elif self.path in ("/api/ajz/detect", "/api/akp02/detect"):
            self._handle_ajz_detect()
        elif self.path == "/api/lcd/detect":
            self._handle_lcd_detect()
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
        elif self.path.split("?")[0] == "/kraken.html":
            self.send_response(301)
            self.send_header("Location", "/dial.html")
            self.end_headers()
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
            if _app and _app.cfg.get("theme"):
                broadcast({"type": "theme", "theme": _app.cfg["theme"]})
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
            if "open_with_notes" in body:
                try:
                    from shell_open import set_open_with
                    set_open_with(bool(body["open_with_notes"]))
                except Exception as e:
                    log.warning("[http] failed to apply open_with_notes: %s", e)
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
                try:
                    import plugin_manager
                    if plugin_manager._active_themed_plugin or plugin_manager._active_themed_exe:
                        plugin_manager._saved_base_theme = dict(body["theme"])
                except Exception:
                    pass
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

    def log_message(self, fmt, *args):
        # suppress per-request logs
        pass


def _get_plugin_state():
    import plugin_manager
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
    return _vision_sensors(_app)


def _save_vision_config():
    _save_vision_config(_app)


def _normalize_sensor(body, existing=None):
    return _normalize_sensor(body, existing)


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

from server.audio import get_volume as _get_volume, get_master_volume as _get_master_volume
from server.discovery import start_udp_discovery


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
    try:
        server = _QuietThreadingHTTPServer((host, port), handler)
        log.info("HTTP server listening on %s:%d (serving %s)", host, port, _HTML_DIR)
        server.serve_forever()
    except OSError as e:
        if getattr(e, "winerror", None) == 10048 or getattr(e, "errno", None) == 10048:
            log.warning("HTTP server port %d is already in use (another instance may be running).", port)
            return
        raise


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
