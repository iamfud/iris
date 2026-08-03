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
        return False
    exe_lower = exe_name.lower().strip()
    try:
        import psutil
        for proc in psutil.process_iter(["name"]):
            try:
                if proc.info["name"] and proc.info["name"].lower() == exe_lower:
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    except Exception:
        return False
    return False


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

    def __init__(self, cfg, serial_sender=None):
        self._cfg = cfg
        self._serial = serial_sender
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

    # ── Config access ────────────────────────────────────────────

    def _plugin_cfg(self):
        return self._cfg.get("plugins", {}).get("vision", {})

    def _sensors(self):
        return self._plugin_cfg().get("sensors", [])

    def _outputs(self):
        return self._plugin_cfg().get("outputs", {})

    def _should_run(self, sensor):
        pcfg = self._plugin_cfg()
        if not pcfg.get("enabled", True):
            return False
        current = next((s for s in pcfg.get("sensors", [])
                        if s.get("id") == sensor.get("id")), None)
        if current is None:
            return False
        if not current.get("enabled", True):
            return False
        return _is_exe_running(current.get("exe", ""))

    # ── Tick loop (hot-apply config) ─────────────────────────────

    def _tick_loop(self):
        while not self._stop.is_set():
            try:
                self._sync()
            except Exception:
                log.exception("vision tick error")
            self._stop.wait(_TICK_S)

    def _sync(self):
        sensors = self._sensors()
        active_ids = {s["id"] for s in sensors if s.get("enabled", True)
                      and _is_exe_running(s.get("exe", ""))}

        with self._lock:
            thread_ids = set(self._threads.keys())

        for sid in thread_ids - active_ids:
            self._stop_sensor(sid)

        for sid in active_ids - thread_ids:
            sensor = next(s for s in sensors if s["id"] == sid)
            self._start_sensor(sensor)

        # Restart crashed threads.
        for sid in active_ids & thread_ids:
            with self._lock:
                t = self._threads.get(sid)
            if t and not t.is_alive():
                self._stop_sensor(sid)
                sensor = next(s for s in sensors if s["id"] == sid)
                self._start_sensor(sensor)

    def _start_sensor(self, sensor):
        with self._lock:
            if sensor["id"] in self._threads:
                return
            self._runtime.setdefault(sensor["id"], {
                "value": 0.0, "active": False, "last_triggered": 0.0, "last_run": 0.0,
            })
            t = threading.Thread(
                target=self._sensor_loop, args=(sensor,),
                daemon=True, name=f"vision-{sensor['id']}")
            self._threads[sensor["id"]] = t
        t.start()

    def _stop_sensor(self, sensor_id):
        with self._lock:
            self._threads.pop(sensor_id, None)

    # ── Per-sensor capture loop ──────────────────────────────────

    def _sensor_loop(self, sensor):
        sid = sensor["id"]
        try:
            while not self._stop.is_set():
                current = next((s for s in self._sensors()
                                if s.get("id") == sid), None)
                if current is None or not current.get("enabled", True):
                    break
                sensor = current
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
        if not sensor.get("output_display", False):
            return
        outputs = self._outputs()
        if outputs.get("display", True) is False:
            return
        if self._serial is None:
            return
        title = sensor.get("event_name") or sensor.get("name") or "Vision"
        message = sensor.get("event_message") or ""
        key = self._display_key(sensor, "notify")
        try:
            if hasattr(self._serial, "notify"):
                self._serial.notify(key, title, message, style="emphasis")
            else:
                self._serial.send_notification(title, message, key=key)
            log.info("[vision] event: %s (value=%.2f)", title, value)
        except Exception:
            log.warning("vision notification failed", exc_info=True)

    def _flash(self, sensor, on):
        if not sensor.get("output_display", False):
            return
        outputs = self._outputs()
        if outputs.get("display", True) is False:
            return
        if self._serial is None:
            return
        key = self._display_key(sensor, "alert")
        try:
            if on:
                name = sensor.get("name") or sensor.get("event_name") or "Vision"
                letters = "".join(c for c in name if c.isalnum())[:4].upper()
                if not letters:
                    letters = "!!!!"
                if hasattr(self._serial, "alert"):
                    self._serial.alert(key, letters, mode="blink", lifetime="hold")
                log.info("[vision] alert on: %s", letters)
            else:
                if hasattr(self._serial, "clear_display"):
                    self._serial.clear_display(key)
                log.info("[vision] alert off")
        except Exception:
            log.warning("vision flash failed", exc_info=True)

    # ── State for UI ─────────────────────────────────────────────

    def poll(self):
        sensors = self._sensors()
        with self._lock:
            runtime = {k: dict(v) for k, v in self._runtime.items()}
        enabled = [s for s in sensors if s.get("enabled", True)]
        active_count = 0
        sensor_rows = []
        for s in sensors:
            rt = runtime.get(s["id"], {})
            if s.get("enabled", True) and rt.get("active"):
                active_count += 1
            sensor_rows.append({
                "id": s["id"],
                "name": s.get("name", ""),
                "exe": s.get("exe", ""),
                "running": s["id"] in self._threads,
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
