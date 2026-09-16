"""System, media, keyboard, and OS interaction HTTP route handlers for Iris server."""

import logging
import os

log = logging.getLogger("iris.server.system")


class SystemHandlerMixin:
    """Provides system, clipboard, media, keyboard, and OS routes to RequestHandler."""

    def _get_app_ref(self):
        try:
            import ws_bridge
            return getattr(ws_bridge, "_app", None)
        except Exception:
            return None

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

    def _handle_sound_preview(self, name):
        import alarm_sound
        ok = alarm_sound.play(name)
        self._send_json({"ok": ok})

    def _handle_sound_stop(self):
        import alarm_sound
        alarm_sound.stop()
        self._send_json({"ok": True})

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
            app = self._get_app_ref()
            current = (app.cfg.get("media_player_path", "") or "") if app is not None else ""
            self._send_json({"ok": True, "players": players, "current": current})
        except Exception as e:
            log.warning("[http] detect media players failed: %s", e)
            self._send_json({"ok": False, "players": [], "current": "", "error": str(e)})

    def _handle_media_art(self):
        """Serve the currently playing album/song artwork (JPEG/PNG)."""
        art_bytes = None
        mime = "image/jpeg"
        art_id = ""
        app = self._get_app_ref()
        try:
            if app is not None and getattr(app, "_providers", None):
                for p in app._providers:
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
            app = self._get_app_ref()
            root = getattr(app, "_root", None) if app is not None else None
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

    def _handle_kraken_detect(self):
        """Return Kraken LCD probe status from the rgb plugin or entity bus."""
        import plugin_manager
        inst = plugin_manager.get("rgb")
        if inst and hasattr(inst, "get_kraken_status"):
            data = inst.get_kraken_status()
        else:
            data = {"found": False}
        self._send_json(data)
