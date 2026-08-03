"""Media provider — now-playing track info.
Sources: Windows SMTC (Spotify, Chrome, Edge), iTunes COM API fallback."""

import asyncio
import logging
import threading
import time

import pystray

from display_priority import PRIO_CORE_NOTIFY

log = logging.getLogger("iris.media")

SMTC_AVAILABLE = False
try:
    import winrt.windows.media.control as wmc
    SMTC_AVAILABLE = True
except ImportError:
    pass

STATUS_ICONS = {
    "playing": "\u25b6",
    "paused": "\u23f8",
    "stopped": "\u266a",
}


_itunes_retry_at = 0.0
_itunes_app = None


def _read_itunes():
    global _itunes_retry_at, _itunes_app
    now = time.time()
    if now < _itunes_retry_at:
        return None
    try:
        import psutil
        if not any(p.name().lower() == "itunes.exe" for p in psutil.process_iter(["name"])):
            _itunes_retry_at = time.time() + 30.0
            _itunes_app = None
            return None
        if _itunes_app is None:
            from comtypes.client import CreateObject
            _itunes_app = CreateObject("iTunes.Application")
        state = _itunes_app.PlayerState
        track = _itunes_app.CurrentTrack
        if not track:
            return None
        result = {
            "title": str(track.Name or ""),
            "artist": str(track.Artist or ""),
            "album": str(track.Album or ""),
        }
        result["status"] = "playing" if state == 1 else ("paused" if state == 2 else "stopped")
        return result
    except Exception:
        _itunes_retry_at = time.time() + 30.0
        _itunes_app = None
        return None


class MediaProvider:
    def __init__(self, cfg, serial_sender=None):
        self.cfg = cfg
        self.serial = serial_sender
        self._track = ""
        self._artist = ""
        self._album = ""
        self._status = "stopped"
        self._last_notify_key = ""
        self._lock = threading.Lock()
        self._running = False

    def start(self):
        self._running = True
        threading.Thread(target=self._loop, daemon=True, name="media-provider").start()

    def stop(self):
        self._running = False

    def _read_smtc(self, loop):
        if not SMTC_AVAILABLE:
            return None
        try:
            mgr = getattr(self, "_smtc_mgr", None)
            if mgr is None:
                mgr = loop.run_until_complete(
                    wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
                )
                self._smtc_mgr = mgr
            session = mgr.get_current_session()
            if not session:
                return None
            props = loop.run_until_complete(
                session.try_get_media_properties_async()
            )
            info = session.get_playback_info()
            status = str(info.playback_status).rsplit(".", 1)[-1].lower()
            if not props.title:
                return None
            return {
                "title": props.title or "",
                "artist": props.artist or "",
                "album": props.album_title or "",
                "status": status,
            }
        except Exception as e:
            log.debug(f"[media] SMTC error: {e}")
            self._smtc_mgr = None
            return None

    def _poll(self, loop):
        while self._running:
            data = None
            if loop:
                data = self._read_smtc(loop)
            if not data or not data.get("title"):
                data = _read_itunes()

            with self._lock:
                if data and data.get("title"):
                    self._track = data["title"]
                    self._artist = data.get("artist", "")
                    self._album = data.get("album", "")
                    self._status = data.get("status", "playing")
                else:
                    self._track = ""
                    self._artist = ""
                    self._album = ""
                    self._status = "stopped"

            track_key = f"{self._track}|{self._artist}"
            if track_key and track_key != self._last_notify_key and self.serial:
                self._last_notify_key = track_key
                msg = f"{self._artist} - {self._track}" if self._artist else self._track
                self.serial.send_notification(
                    "Now Playing", msg, priority=PRIO_CORE_NOTIFY, key="media.now")
            elif not track_key and self._last_notify_key:
                if self.serial:
                    self.serial.send_notification(
                        "Media", "Playback ended",
                        priority=PRIO_CORE_NOTIFY, key="media.now")
                self._last_notify_key = ""
                self._smtc_mgr = None

            time.sleep(3)

    def _loop(self):
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 2)
        loop = None
        if SMTC_AVAILABLE:
            try:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                mgr = loop.run_until_complete(
                    wmc.GlobalSystemMediaTransportControlsSessionManager.request_async()
                )
                self._smtc_mgr = mgr
            except Exception as e:
                log.warning(f"[media] SMTC init failed: {e}")
        self._poll(loop)

    def menu_items(self):
        with self._lock:
            track = self._track
            artist = self._artist
            status = self._status
        if not track:
            return [pystray.MenuItem("\u266a No track", None, enabled=False)]
        icon = STATUS_ICONS.get(status, "\u266a")
        label = f"{icon} {track}"
        if artist:
            label += f" \u2014 {artist}"
        return [pystray.MenuItem(label, None, enabled=False)]

    def poll_data(self):
        with self._lock:
            return {
                "title": self._track,
                "artist": self._artist,
                "album": self._album,
                "status": self._status,
            }
