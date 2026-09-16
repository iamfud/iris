"""Notifications API handler mixin for Iris server."""

class NotificationsHandlerMixin:
    """Provides notification store manipulation routes to RequestHandler."""

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
            body = self._read_json() or {}
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
