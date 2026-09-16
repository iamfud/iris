"""Vision sensors API handler mixin for Iris server."""

import logging
import time

log = logging.getLogger("iris.server.vision")


def vision_sensors(app):
    """Return the (mutable) list of vision sensors from app config."""
    if app is None:
        return []
    return app.cfg.setdefault("plugins", {}).setdefault("vision", {}).setdefault("sensors", [])


def save_vision_config(app):
    if app is None:
        return
    from config import save_config
    save_config(app.cfg)


def normalize_sensor(body, existing=None):
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
    sensor.setdefault("created", int(time.time()))
    return sensor


class VisionHandlerMixin:
    """Provides Vision sensor management routes to RequestHandler."""

    def _get_app_ref(self):
        try:
            import ws_bridge
            return getattr(ws_bridge, "_app", None)
        except Exception:
            return None

    def _handle_vision_capture(self):
        import vision
        app = self._get_app_ref()
        root = app._root if app is not None else None
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
        app = self._get_app_ref()
        if app is None:
            self.send_error(503, "App not registered")
            return
        sensors = vision_sensors(app)
        sensor = normalize_sensor(body, sensors)
        sensors.append(sensor)
        save_vision_config(app)
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
        app = self._get_app_ref()
        sensors = vision_sensors(app)
        idx = next((i for i, s in enumerate(sensors) if s.get("id") == sensor_id), None)
        if idx is None:
            self.send_error(404, "sensor not found")
            return
        sensor = normalize_sensor(body)
        sensor["id"] = sensor_id
        sensor["created"] = sensors[idx].get("created", 0)
        sensors[idx] = sensor
        save_vision_config(app)
        self._send_json({"ok": True, "sensor": sensor})

    def _handle_vision_delete_sensor(self, sensor_id):
        if not self._is_loopback_peer():
            self.send_error(403, "Forbidden")
            return
        app = self._get_app_ref()
        sensors = vision_sensors(app)
        before = len(sensors)
        sensors[:] = [s for s in sensors if s.get("id") != sensor_id]
        save_vision_config(app)
        self._send_json({"ok": len(sensors) < before})
