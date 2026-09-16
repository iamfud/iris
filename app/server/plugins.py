"""Plugin management API handler mixin for Iris server."""

import logging
import os

log = logging.getLogger("iris.server.plugins")


class PluginsHandlerMixin:
    """Provides plugin HTTP route handlers to RequestHandler."""

    def _get_app_ref(self):
        try:
            import ws_bridge
            return getattr(ws_bridge, "_app", None)
        except Exception:
            return None

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

    def _handle_save_plugin_config(self, name):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
        try:
            body = self._read_json()
        except Exception as e:
            self.send_error(400, str(e))
            return
        app = self._get_app_ref()
        if name == "matrix_display":
            if app and isinstance(body, dict):
                from config import save_config
                if "brightness" in body:
                    try:
                        app._set_brightness(max(0, min(4, int(body["brightness"]))))
                    except Exception:
                        pass
                app.cfg.update(body)
                save_config(app.cfg)
                self._push_config_to_device(body)
                import ws_bridge
                ws_bridge.broadcast({"type": "config", "config": body})
            self._send_json({"ok": True})
            return

        import plugin_manager
        if name == "vision":
            from ws_bridge import _merge_vision_config
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
