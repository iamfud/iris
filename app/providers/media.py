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
_itunes_prev_key = ""
_itunes_prev_art = None


def _read_itunes():
    global _itunes_retry_at, _itunes_app, _itunes_prev_key, _itunes_prev_art
    now = time.time()
    if now < _itunes_retry_at:
        return None
    try:
        from win_platform import is_process_running
        if not is_process_running("itunes.exe", ttl=1.0):
            _itunes_retry_at = time.time() + 30.0
            _itunes_app = None
            _itunes_prev_key = ""
            _itunes_prev_art = None
            return None
        if _itunes_app is None:
            from comtypes.client import CreateObject
            _itunes_app = CreateObject("iTunes.Application")
        state = _itunes_app.PlayerState
        track = _itunes_app.CurrentTrack
        if not track:
            return None
        title = str(track.Name or "")
        artist = str(track.Artist or "")
        album = str(track.Album or "")
        track_key = f"{title}|{artist}|{album}"

        result = {
            "title": title,
            "artist": artist,
            "album": album,
        }
        result["status"] = "playing" if state == 1 else ("paused" if state == 2 else "stopped")

        # Extract embedded artwork only when track changes
        if track_key == _itunes_prev_key:
            result["art_bytes"] = _itunes_prev_art
        else:
            art_bytes = None
            try:
                art_col = getattr(track, "Artwork", None)
                if art_col and art_col.Count > 0:
                    art = art_col.Item(1)
                    tmp_path = os.path.join(tempfile.gettempdir(), f"iris_itunes_{abs(hash(title))}.jpg")
                    art.SaveArtworkToFile(tmp_path)
                    if os.path.isfile(tmp_path):
                        with open(tmp_path, "rb") as f:
                            art_bytes = f.read()
                        try:
                            os.remove(tmp_path)
                        except Exception:
                            pass
            except Exception:
                pass
            _itunes_prev_key = track_key
            _itunes_prev_art = art_bytes
            result["art_bytes"] = art_bytes

        return result
    except Exception:
        _itunes_retry_at = time.time() + 30.0
        _itunes_app = None
        _itunes_prev_key = ""
        _itunes_prev_art = None
        return None


class MediaProvider:
    def __init__(self, cfg, serial_sender=None):
        self.cfg = cfg
        self.serial = serial_sender
        self._track = ""
        self._artist = ""
        self._album = ""
        self._status = "stopped"
        self._art_bytes = None
        self._art_mime = "image/jpeg"
        self._art_id = ""
        self._prev_smtc_key = ""
        self._prev_smtc_art = None
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
                sessions = mgr.get_sessions()
                if sessions and len(sessions) > 0:
                    session = sessions[0]
            if not session:
                return None
            props = loop.run_until_complete(
                session.try_get_media_properties_async()
            )
            info = session.get_playback_info()
            raw_stat = getattr(info, "playback_status", None)
            if raw_stat == 4 or getattr(raw_stat, "name", "").lower() == "playing" or str(raw_stat).lower() == "playing":
                status = "playing"
            elif raw_stat == 5 or getattr(raw_stat, "name", "").lower() == "paused" or str(raw_stat).lower() == "paused":
                status = "paused"
            else:
                status = "stopped"

            if not props or not props.title:
                return None

            title = props.title or ""
            artist = props.artist or ""
            album = props.album_title or ""
            track_key = f"{title}|{artist}|{album}"

            if track_key == self._prev_smtc_key:
                art_bytes = self._prev_smtc_art
            else:
                art_bytes = None
                if props.thumbnail:
                    try:
                        import winrt.windows.storage.streams as streams
                        t_stream = loop.run_until_complete(props.thumbnail.open_read_async())
                        size = t_stream.size
                        if size > 0:
                            reader = streams.DataReader(t_stream)
                            loop.run_until_complete(reader.load_async(size))
                            buf = bytearray(size)
                            reader.read_bytes(buf)
                            art_bytes = bytes(buf)
                    except Exception as ex:
                        log.debug("[media] SMTC thumbnail read error: %s", ex)
                self._prev_smtc_key = track_key
                self._prev_smtc_art = art_bytes

            return {
                "title": title,
                "artist": artist,
                "album": album,
                "status": status,
                "art_bytes": art_bytes,
            }
        except Exception as e:
            log.debug(f"[media] SMTC error: {e}")
            self._smtc_mgr = None
            return None

    def _poll(self, loop):
        while self._running:
            try:
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
                        new_art = data.get("art_bytes")
                        if new_art:
                            self._art_bytes = new_art
                            track_key = f"{self._track}|{self._artist}"
                            self._art_id = f"{abs(hash(track_key))}_{len(new_art)}"
                        elif self._track != getattr(self, "_prev_track", ""):
                            # Clear old artwork when track changes with no art
                            self._art_bytes = None
                            self._art_id = ""
                        self._prev_track = self._track
                    else:
                        self._track = ""
                        self._artist = ""
                        self._album = ""
                        self._status = "stopped"
                        self._art_bytes = None
                        self._art_id = ""
                        self._prev_track = ""

                track_key = f"{self._track}|{self._artist}"
                if track_key and track_key != self._last_notify_key and self.serial:
                    self._last_notify_key = track_key
                    msg = f"{self._artist} - {self._track}" if self._artist else self._track
                    if hasattr(self.serial, "event_good"):
                        self.serial.event_good("media.now", "Now Playing", msg, priority=PRIO_CORE_NOTIFY)
                    else:
                        self.serial.send_notification("Now Playing", msg, priority=PRIO_CORE_NOTIFY, key="media.now")
                elif not track_key and self._last_notify_key:
                    if self.serial:
                        if hasattr(self.serial, "event"):
                            self.serial.event("media.now", "Media", "Playback ended", status="info", priority=PRIO_CORE_NOTIFY)
                        else:
                            self.serial.send_notification("Media", "Playback ended", priority=PRIO_CORE_NOTIFY, key="media.now")
                    self._last_notify_key = ""
                    self._smtc_mgr = None
            except Exception as e:
                log.debug("[media] poll iteration error: %s", e)

            time.sleep(1.5)

    def _loop(self):
        import ctypes
        ctypes.windll.ole32.CoInitializeEx(None, 0)
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

    def get_artwork(self):
        with self._lock:
            return self._art_bytes, self._art_mime, self._art_id

    def poll_data(self):
        with self._lock:
            return {
                "title": self._track,
                "artist": self._artist,
                "album": self._album,
                "status": self._status,
                "has_art": bool(self._art_bytes),
                "art_id": self._art_id,
            }
