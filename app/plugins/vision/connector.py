"""Vision sensor manager — runs per-sensor capture threads.

Each enabled sensor with a running target exe gets its own capture
thread running at ``poll_rate`` Hz.  The manager re-reads sensor config
every 0.5 s so edits hot-apply without a restart.  A sensor thread
exits as soon as its exe closes, its ``enabled`` flag flips, or the
plugin stops.

Triggered events fire on the rising edge of the threshold crossing,
gated by a per-sensor cooldown and the plugin's Hardware Display output
routing.
"""

import logging
import threading
import time

import vision

log = logging.getLogger("iris.plugins.vision.connector")

_TICK_S = 0.5


def _is_exe_running(exe_name):
    if not exe_name:
        return True
    try:
        from win_platform import is_process_running
        return is_process_running(exe_name, ttl=1.0)
    except Exception:
        return True


def _is_exe_foreground(exe_name):
    """True when a window belonging to *exe_name* is the foreground window."""
    if not exe_name:
        return False
    exe_lower = exe_name.lower().strip()
    try:
        import ctypes
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return False
        import psutil
        name = psutil.Process(pid.value).name()
        return name.lower().strip() == exe_lower
    except Exception:
        return True


class VisionSensorManager:

    def __init__(self, cfg, serial_sender=None, overlays=None):
        self._cfg = cfg
        self._serial = serial_sender
        self._overlays = overlays
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._threads = {}   # sensor_id -> thread
        self._runtime = {}   # sensor_id -> {value, active, last_triggered, last_run}
        self._tick = None

    # ── Lifecycle ────────────────────────────────────────────────

    def start(self):
        self._stop.clear()
        self._tick = threading.Thread(
            target=self._tick_loop, daemon=True, name="vision-manager")
        self._tick.start()

    def stop(self):
        self._stop.set()
        if self._tick and self._tick.is_alive():
            self._tick.join(timeout=2)
        with self._lock:
            threads = list(self._threads.values())
            self._threads.clear()
        for t in threads:
            t.join(timeout=2)
        self._clear_hardware_alerts(None)

    # ── Config access ────────────────────────────────────────────

    def _plugin_cfg(self):
        return self._cfg.get("plugins", {}).get("vision", {})

    def _sensors(self):
        raw_sensors = self._plugin_cfg().get("sensors", [])
        if not isinstance(raw_sensors, list):
            return []
        sensors = []
        seen = set()
        for raw in raw_sensors:
            sensor = vision.sanitize_sensor(raw)
            sensor_id = sensor.get("id")
            if not sensor_id or sensor_id in seen:
                continue
            seen.add(sensor_id)
            anchor = sensor.get("anchor")
            region = sensor.get("region")
            if anchor and region:
                sensor["_bbox"] = vision.region_to_bbox(anchor, region)
            sensor["_target_rgb"] = vision._hex_to_rgb(sensor.get("color"))
            sensor["_sanitized"] = True
            sensors.append(sensor)
        return sensors

    def _outputs(self):
        return self._plugin_cfg().get("outputs", {})

    def _should_run(self, sensor):
        pcfg = self._plugin_cfg()
        if not pcfg.get("enabled", True):
            return False
        if not sensor or not sensor.get("enabled", True):
            return False
        return _is_exe_running(sensor.get("exe", ""))

    # ── Tick loop (hot-apply config) ─────────────────────────────

    def _tick_loop(self):
        while not self._stop.is_set():
            try:
                self._sync()
            except Exception:
                log.exception("vision tick error")
            self._stop.wait(_TICK_S)

    def _sync(self):
        pcfg = self._plugin_cfg()
        plugin_enabled = pcfg.get("enabled", True)
        hw_output_enabled = pcfg.get("outputs", {}).get("display", True)

        if not plugin_enabled or not hw_output_enabled:
            self._clear_hardware_alerts(None)

        sensors = self._sensors()
        with self._lock:
            self._sensors_map = {s.get("id"): s for s in sensors}
            thread_ids = set(self._threads.keys())

        active_ids = {s.get("id") for s in sensors if s.get("enabled", True)
                      and _is_exe_running(s.get("exe", ""))}

        for sid in thread_ids - active_ids:
            self._stop_sensor(sid)

        for s in sensors:
            sid = s.get("id")
            if sid and (not s.get("enabled", True) or not s.get("output_display", True)):
                self._clear_hardware_alerts(sid)

        for sid in active_ids - thread_ids:
            sensor = self._sensors_map.get(sid)
            if sensor is not None:
                self._start_sensor(sensor)

        # Restart crashed threads.
        for sid in active_ids & thread_ids:
            with self._lock:
                t = self._threads.get(sid)
            if t and not t.is_alive():
                self._stop_sensor(sid)
                sensor = self._sensors_map.get(sid)
                if sensor is not None:
                    self._start_sensor(sensor)

    def _start_sensor(self, sensor):
        sid = sensor.get("id")
        with self._lock:
            if sid in self._threads:
                return
            self._runtime.setdefault(sid, {
                "value": 0.0, "active": False, "last_triggered": 0.0, "last_run": 0.0,
            })
            t = threading.Thread(
                target=self._sensor_loop, args=(sid,),
                daemon=True, name=f"vision-{sid}")
            self._threads[sid] = t
        t.start()

    def _stop_sensor(self, sensor_id):
        with self._lock:
            self._threads.pop(sensor_id, None)
        self._clear_hardware_alerts(sensor_id)

    # ── Per-sensor capture loop ──────────────────────────────────

    def _sensor_loop(self, sid):
        try:
            while not self._stop.is_set():
                with self._lock:
                    sensor = getattr(self, "_sensors_map", {}).get(sid)
                if sensor is None or not sensor.get("enabled", True):
                    break
                if not self._should_run(sensor):
                    break
                try:
                    if sensor.get("require_foreground", False):
                        in_fg = _is_exe_foreground(sensor.get("exe", ""))
                    else:
                        in_fg = True
                    if in_fg:
                        result = vision.measure(sensor)
                        value = result["value"]
                        active = result["active"]
                    else:
                        value = 0.0
                        active = False
                except Exception:
                    log.warning("vision measure failed for %s", sid, exc_info=True)
                    value = 0.0
                    active = False

                now = time.time()
                with self._lock:
                    rt = self._runtime.setdefault(sid, {
                        "value": 0.0, "active": False,
                        "last_triggered": 0.0, "last_run": 0.0,
                    })
                    prev_active = rt["active"]
                    rt["value"] = value
                    rt["last_run"] = now

                try:
                    import automations
                    automations.get_engine().dispatch_state(
                        "vision", sid,
                        {"value": value, "active": active, "name": sensor.get("name", ""), "mode": sensor.get("mode", "")}
                    )
                except Exception:
                    pass

                if active and not prev_active:
                    cooldown = float(sensor.get("cooldown_s", 10.0))
                    with self._lock:
                        last = rt["last_triggered"]
                    if now - last >= cooldown:
                        with self._lock:
                            rt["last_triggered"] = now
                        if sensor.get("flash_name", False):
                            self._flash(sensor, True)
                        else:
                            self._fire(sensor, value)
                elif not active and prev_active:
                    if sensor.get("flash_name", False):
                        self._flash(sensor, False)

                with self._lock:
                    rt["active"] = active

                rate = float(sensor.get("poll_rate", 1.0))
                rate = max(0.1, min(rate, 10.0))
                self._stop.wait(rate)
        finally:
            with self._lock:
                self._threads.pop(sid, None)

    # ── Event dispatch ───────────────────────────────────────────

    def _display_key(self, sensor, kind):
        sid = sensor.get("id") or sensor.get("name") or "sensor"
        return f"vision.{sid}.{kind}"

    def _fire(self, sensor, value):
        title = sensor.get("event_name") or sensor.get("name") or "Vision Alert"
        raw_msg = sensor.get("event_message")
        if raw_msg:
            try:
                message = raw_msg.replace("{value}", str(value)).replace("{text}", str(value))
            except Exception:
                message = raw_msg
        else:
            if isinstance(value, (int, float)):
                message = f"Sensor triggered (value: {value:.1f})"
            elif isinstance(value, str) and value:
                message = f"Sensor triggered: {value}"
            else:
                message = "Sensor triggered"
        key = self._display_key(sensor, "alert")

        # 1. Play sound if enabled on sensor
        if sensor.get("play_sound", False):
            try:
                import alarm_sound
                alarm_sound.play_one_shot(sensor.get("sound_name", "remind"))
            except Exception:
                pass

        # 2. Desktop Overlay Dispatch
        if self._overlays is not None:
            try:
                self._overlays.hero(
                    title=title,
                    subtitle=message,
                    fields=[("Sensor", (sensor.get("name") or "Vision").strip()), ("Status", "ALERT")],
                    duration=5,
                )
            except Exception as e:
                log.debug("[vision] overlay alert error: %s", e)

        # 3. Native Iris Serial Alert Dispatch
        if self._serial is not None:
            try:
                if hasattr(self._serial, "send_alert"):
                    self._serial.send_alert(title, message, key=key)
                elif hasattr(self._serial, "event_bad"):
                    self._serial.event_bad(key, title, message)
                log.info("[vision] send_alert dispatched: %s - %s", title, message)
            except Exception:
                log.warning("vision send_alert failed", exc_info=True)
        else:
            try:
                import ws_bridge
                import panel_runtime
                toast_data = {
                    "app": (sensor.get("name") or "Vision").strip(),
                    "title": title,
                    "body": message,
                    "theme": "alert",
                    "status": "bad",
                    "timestamp": int(time.time()),
                }
                ws_bridge.broadcast({
                    "type": "event",
                    **toast_data,
                })
            except Exception:
                pass

    def _flash(self, sensor, on):
        if on:
            title = sensor.get("event_name") or sensor.get("name") or "Vision Alert"
            message = sensor.get("event_message") or f"{title} active"
            key = self._display_key(sensor, "alert")

            # 1. Play sound if enabled on sensor
            if sensor.get("play_sound", False):
                try:
                    import alarm_sound
                    alarm_sound.play_one_shot(sensor.get("sound_name", "remind"))
                except Exception:
                    pass

            # 2. Native Iris Alert Dispatch (WebPortal + priority)
            if self._serial is not None:
                try:
                    if hasattr(self._serial, "send_alert"):
                        self._serial.send_alert(title, message, key=key)
                    elif hasattr(self._serial, "event_bad"):
                        self._serial.event_bad(key, title, message)
                except Exception:
                    log.warning("vision send_alert failed", exc_info=True)

            # 3. Hardware Display 4-character blink (5 flashes)
            if sensor.get("output_display", True):
                outputs = self._outputs()
                if outputs.get("display", True) is not False and self._serial is not None:
                    name = sensor.get("name") or sensor.get("event_name") or "Vision"
                    letters = "".join(c for c in name if c.isalnum())[:4].upper()
                    if not letters:
                        letters = "!!!!"
                    try:
                        if hasattr(self._serial, "alert"):
                            self._serial.alert(key, letters, mode="blink", lifetime="timed", timed_s=2.5)
                        log.info("[vision] alert on (5 flashes): %s", letters)
                    except Exception:
                        log.warning("vision flash failed", exc_info=True)
        else:
            sid = sensor.get("id") or sensor.get("name")
            self._clear_hardware_alerts(sid)
            log.info("[vision] alert off")

    def _clear_hardware_alerts(self, sid=None):
        if self._serial is None:
            return
        try:
            if sid:
                for kind in ("alert", "notify"):
                    key = self._display_key({"id": sid}, kind)
                    for m in ("clear", "clear_display"):
                        if hasattr(self._serial, m):
                            getattr(self._serial, m)(key)
            else:
                for m in ("clear_prefix", "clear_display_prefix"):
                    if hasattr(self._serial, m):
                        getattr(self._serial, m)("vision.")
        except Exception as ex:
            log.debug("[vision] clear hardware alert failed: %s", ex)

    # ── State for UI ─────────────────────────────────────────────

    def poll(self):
        sensors = self._sensors()
        with self._lock:
            runtime = {k: dict(v) for k, v in self._runtime.items()}
        enabled = [s for s in sensors if s.get("enabled", True)]
        active_count = 0
        sensor_rows = []
        for s in sensors:
            rt = runtime.get(s.get("id"), {})
            if s.get("enabled", True) and rt.get("active"):
                active_count += 1
            sensor_rows.append({
                "id": s.get("id"),
                "name": s.get("name", ""),
                "exe": s.get("exe", ""),
                "running": s.get("id") in self._threads,
                "value": rt.get("value", 0.0),
                "active": rt.get("active", False),
                "last_run": rt.get("last_run", 0.0),
            })
        return {
            "available": True,
            "state": {
                "sensor_count": len(enabled),
                "active_events": active_count,
            },
            "sensors": sensor_rows,
        }

    def snapshot(self):
        data = self.poll()
        data["config"] = list(self._sensors())
        return data
