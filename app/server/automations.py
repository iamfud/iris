"""Automations API handler mixin for Iris server."""

import time


class AutomationsHandlerMixin:
    """Provides automations routes to RequestHandler."""

    def _get_app_ref(self):
        try:
            import ws_bridge
            return getattr(ws_bridge, "_app", None)
        except Exception:
            return None

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
        app = self._get_app_ref()
        if app is None:
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

        engine.save_rules(rules, app.cfg)
        self._send_json({"ok": True, "rule": rule})

    def _handle_delete_automation(self, rule_id):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
        app = self._get_app_ref()
        if app is None:
            self.send_error(503, "App not registered")
            return
        import automations
        engine = automations.get_engine()
        rules = [r for r in engine.get_rules() if r.get("id") != rule_id]
        engine.save_rules(rules, app.cfg)
        self._send_json({"ok": True})

    def _handle_automations_disclaimer_ack(self):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
        app = self._get_app_ref()
        if app is None:
            self.send_error(503, "App not registered")
            return
        import automations
        engine = automations.get_engine()
        engine.set_disclaimer_ack(True)
        app.cfg["automations_disclaimer_ack"] = True
        try:
            from config import save_config
            save_config(app.cfg)
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
