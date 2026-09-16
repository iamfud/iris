"""Audio devices and volume control API handler mixin for Iris server."""

import logging

log = logging.getLogger("iris.server.audio")


class AudioHandlerMixin:
    """Provides audio device listing and volume control routes to RequestHandler."""

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
        """Set a specific app session's volume or mute."""
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


def get_volume():
    import win_volume
    try:
        return win_volume.get_active_app_state()
    except Exception as e:
        log.warning("[http] volume query failed: %s", e)
        return {"app": None, "volume": None}


def get_master_volume():
    import win_volume
    try:
        return win_volume.get_master_state()
    except Exception as e:
        log.warning("[http] master volume query failed: %s", e)
        return {"volume": None}

