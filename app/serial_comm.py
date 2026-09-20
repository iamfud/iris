"""Iris — Serial communication and device bridge.

Manages USB serial connection to the D1 Mini.
Pushes settings on reconnect, provides time sync,
and delivers STATS lines from providers to the device.
"""

import json
import logging
import queue
import threading
import time

from constants import DEVICE_DEFAULTS
from device_profile import MATRIX, profile_for
from display_manager import DisplayManager
from display_priority import PRIO_PLUGIN_NOTIFY

log = logging.getLogger("iris.serial")

try:
    import serial
    import serial.tools.list_ports
    SERIAL_AVAILABLE = True
except ImportError:
    SERIAL_AVAILABLE = False

ESP32_VIDS = {0x10C4, 0x1A86, 0x0403, 0x067B, 0x303A}


def _local_utc_offset():
    import datetime as _dt
    t = _dt.datetime.now(_dt.timezone.utc).astimezone()
    return int(t.utcoffset().total_seconds())


class SerialSender:
    def __init__(self):
        self._lock = threading.RLock()
        self._write_lock = threading.Lock()
        self._forced_port = None
        self._ser = None
        self._on_connect_queue = {}
        self._rx_q = queue.Queue(maxsize=64)
        self._dispatch_q = queue.Queue(maxsize=256)
        self._line_callbacks = []
        self._time_sync_interval = 60.0
        self._last_time_sync = 0.0
        self._dispatch_stop = threading.Event()
        self._last_drop_warn = 0.0
        self._profile = MATRIX
        self._profile_checked = False
        # Device-agnostic intent arbiter (text + progress). Wire emits go
        # through _write_locked; callers must already hold self._lock or use
        # the public wrappers that take the lock.
        self._display = DisplayManager(
            write_fn=self._write_locked,
            profile_fn=lambda: self._profile,
        )
        threading.Thread(target=self._keepalive, daemon=True, name="serial-keepalive").start()
        threading.Thread(target=self._reader, daemon=True, name="serial-reader").start()
        threading.Thread(target=self._dispatcher, daemon=True, name="serial-dispatcher").start()
        threading.Thread(target=self._time_sync_loop, daemon=True, name="serial-timesync").start()
        threading.Thread(target=self._display_arbiter, daemon=True, name="display-arbiter").start()

    # ── Public API ────────────────────────────────────────────

    def add_line_callback(self, cb):
        self._line_callbacks.append(cb)

    def queue_on_connect(self, key, value):
        with self._lock:
            self._on_connect_queue[key] = value

    def queue_on_connect_default(self, key, value):
        with self._lock:
            self._on_connect_queue.setdefault(key, value)

    def set_port(self, port_name):
        with self._lock:
            new_forced = None if port_name == "auto" else port_name
            if new_forced == self._forced_port:
                return
            self._forced_port = new_forced
            if self._ser:
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None

    def connected_port(self):
        with self._lock:
            if self._ser and self._ser.is_open:
                return self._ser.port
        return None

    @property
    def is_connected(self) -> bool:
        return self.connected_port() is not None


    def set_live(self, key, value):
        return self._write(f"SET:{key}={value}\n")

    def send_stats(self, cpu_pct, cpu_temp, gpu_temp, fps):
        c = f"{cpu_pct:.0f}"
        t = f"{cpu_temp:.0f}" if cpu_temp is not None else "-"
        g = f"{gpu_temp:.0f}" if gpu_temp is not None else "-"
        f = f"{min(fps, 999):.0f}" if fps is not None else "-"
        self._write(f"STATS:{c}|{t}|{g}|{f}\n")

    # ── Display intents (device-agnostic; plugins should prefer these) ──

    def notify(self, key, title, message, priority=PRIO_PLUGIN_NOTIFY, style="normal", theme="purple"):
        """Persistent inbox notification (saved in notifications.json).

        ``theme``: ``purple`` (standard) or ``alert`` (red rapid-flash toast).
        """
        with self._lock:
            self._display.notify(key, title, message, priority=priority, style=style, theme=theme)

    def send_alert(self, title, message, key=None):
        """Red alert notification — persistent inbox + rapid-flash toast.

        Plugin-friendly: ``self.serial.send_alert("Health Low", "Hull below 30%")``.
        """
        from display_priority import PRIO_PLUGIN_ALERT
        self.notify(key or f"alert.{title}", title, message,
                    priority=PRIO_PLUGIN_ALERT, style="emphasis", theme="alert")

    def set_warning(self, key, color=None, message=""):
        """Flag a panel button as in warning state (button turns warning colour).

        Plugin-friendly: ``self.serial.set_warning("elite_dangerous:shields",
        color="#ffaa00", message="Shields failing")``. ``color`` may be a hex
        string or ``None`` for the panel's default warning colour. The warning
        stays active until :meth:`clear_warning` is called.
        """
        import warning_state
        warning_state.set_warning(key, color=color, message=message)

    def clear_warning(self, key):
        """Remove a warning previously set with :meth:`set_warning`."""
        import warning_state
        warning_state.clear_warning(key)

    def event(self, key, title, message, status="good", priority=PRIO_PLUGIN_NOTIFY, style="normal"):
        """Transient event (Green/Red theme, 5s on phone panel, gone for good, never stored in inbox)."""
        with self._lock:
            self._display.event(key, title, message, status=status, priority=priority, style=style)

    def event_good(self, key, title, message, priority=PRIO_PLUGIN_NOTIFY, style="normal"):
        """Transient good/success event (Green theme)."""
        self.event(key, title, message, status="good", priority=priority, style=style)

    def event_success(self, key, title, message, priority=PRIO_PLUGIN_NOTIFY, style="normal"):
        """Alias for event_good (Green theme)."""
        self.event(key, title, message, status="good", priority=priority, style=style)

    def event_bad(self, key, title, message, priority=PRIO_PLUGIN_NOTIFY, style="normal"):
        """Transient bad/warning event (Red theme)."""
        self.event(key, title, message, status="bad", priority=priority, style=style)

    def event_warning(self, key, title, message, priority=PRIO_PLUGIN_NOTIFY, style="normal"):
        """Alias for event_bad (Red theme)."""
        self.event(key, title, message, status="bad", priority=priority, style=style)

    def event_alert(self, key, title, message, priority=PRIO_PLUGIN_NOTIFY, style="normal"):
        """Alias for event_bad (Red theme)."""
        self.event(key, title, message, status="bad", priority=priority, style=style)

    def alert(self, key, text, *, mode="blink", lifetime="hold",
              timed_s=5.0, priority=None):
        """High-priority ≤4-char alert (hold or timed)."""
        from display_priority import PRIO_PLUGIN_ALERT
        if priority is None:
            priority = PRIO_PLUGIN_ALERT
        with self._lock:
            self._display.alert(
                key, text, mode=mode, lifetime=lifetime,
                timed_s=timed_s, priority=priority)

    def sticky(self, key, title, message, *, ttl_s=None, priority=PRIO_PLUGIN_NOTIFY):
        """Scroll once, then hold until clear/ttl/preempt."""
        with self._lock:
            self._display.sticky(
                key, title, message, ttl_s=ttl_s, priority=priority)

    def clear_display(self, key):
        """Dismiss text intent with this key."""
        with self._lock:
            self._display.clear(key)

    def clear_display_prefix(self, prefix):
        """Dismiss all text intents whose key starts with prefix."""
        with self._lock:
            self._display.clear_prefix(prefix)

    def send_notification(self, title, message, priority=PRIO_PLUGIN_NOTIFY, key=None):
        """Backward-compatible notify. Prefer ``notify(key, ...)``."""
        if key is None:
            key = f"notify.{priority}.{title}"
        self.notify(key, title, message, priority=priority)

    def claim_progress(self, claim_id, priority, name, pct,
                       keepalive_s=3.0, ttl_s=10.0):
        """Register or refresh a persistent progress-bar claim."""
        with self._lock:
            self._display.claim_progress(
                claim_id, priority, name, pct,
                keepalive_s=keepalive_s, ttl_s=ttl_s)

    def remind_progress(self, claim_id, priority, name, pct,
                        on_s=3.0, period_s=10.0):
        """Register or refresh a reminder progress claim."""
        with self._lock:
            self._display.remind_progress(
                claim_id, priority, name, pct,
                on_s=on_s, period_s=period_s)

    def release_progress(self, claim_id):
        """Remove a progress-bar claim."""
        with self._lock:
            self._display.release_progress(claim_id)

    def release_progress_prefix(self, prefix):
        with self._lock:
            self._display.release_progress_prefix(prefix)

    def send_progress(self, name, percent):
        """Direct PROG write (bypasses claims). Prefer claim_progress."""
        if percent is None or percent < 0:
            self._write("PROG:OFF\n")
            return
        name = name.replace("|", " ").replace("\n", " ")[:self._profile.progress_name_max_full]
        pct = max(0, min(100, int(percent)))
        self._write(f"PROG:{name}|{pct}\n")

    def send_vision_notification(self, title, message, key=None):
        """Deprecated: use notify(..., style='emphasis')."""
        self.notify(key or "vision.notify", title, message, style="emphasis")

    def send_vision_flash(self, text, key=None):
        """Deprecated: use alert(key, text)."""
        self.alert(key or "vision.alert", text, mode="blink", lifetime="hold")

    def clear_vision_flash(self, key=None):
        """Deprecated: use clear_display(key)."""
        self.clear_display(key or "vision.alert")

    def _send_command(self, cmd, payload):
        return self._write(f"{cmd}:{payload}\n")

    def send_vc_join(self, name):
        self._send_command("VC", name.replace("\n", " ")[:48])

    def factory_reset(self):
        sent = 0
        for key, val in DEVICE_DEFAULTS.items():
            if self.set_live(key, val):
                sent += 1
        log.info("[serial] factory reset sent %d SET commands", sent)

    def factory_reset_with_reboot(self):
        self.factory_reset()
        time.sleep(0.5)
        self.reset_device()
        with self._lock:
            self._on_connect_queue.clear()
            for key, val in DEVICE_DEFAULTS.items():
                self._on_connect_queue[key] = val
            if self._ser:
                try:
                    self._ser.close()
                except Exception:
                    pass
                self._ser = None
        log.info("[serial] factory reset done; device defaults re-queued")

    def reset_device(self):
        ser = None
        with self._lock:
            if not self._ser or not self._ser.is_open:
                log.warning("[serial] reset: no serial connection")
                return False
            ser = self._ser
            port = ser.port

        try:
            log.info("[serial] pulsing DTR+RTS on %s", port)
            with self._write_lock:
                ser.dtr = True
                ser.rts = True
                time.sleep(0.1)
                ser.dtr = False
                ser.rts = False
                time.sleep(0.1)
                ser.dtr = True
                ser.rts = True
                time.sleep(0.1)
                ser.dtr = False
                ser.rts = False
            # Wait outside lock for device reboot
            time.sleep(2.5)
        except Exception as e:
            log.warning("[serial] DTR/RTS reset failed: %s", e)
            with self._lock:
                if self._ser is ser:
                    try:
                        self._ser.close()
                    except Exception:
                        pass
                    self._ser = None
            return False
        log.info("[serial] device reset via DTR/RTS on %s", port)
        return True

    def get_config(self, timeout=5):
        _, resp = self._send_and_wait("GET:config", prefix="CONFIG:", timeout=timeout)
        if resp and resp.startswith("CONFIG:"):
            try:
                return json.loads(resp[7:])
            except Exception:
                pass
        return None

    def detect_hardware(self, timeout=5):
        ok, resp = self._send_and_wait("IDENT?", prefix="IDENT:", timeout=timeout)
        if ok and resp and resp.startswith("IDENT:"):
            hw_id = resp[6:].strip()
            return hw_id
        return None

    # ── Internal ──────────────────────────────────────────────

    def _display_arbiter(self):
        """1s ticker: progress keepalives + text promote/timeout."""
        while True:
            time.sleep(1.0)
            try:
                self._display.tick()
            except Exception:
                log.exception("[serial] display arbiter error")

    def _write(self, line):
        return self._write_locked(line)

    def _write_locked(self, line):
        raw = line.encode("utf-8") if isinstance(line, str) else line
        with self._lock:
            ser = self._ser
        if not (ser and ser.is_open):
            return False
        with self._write_lock:
            if not (ser and ser.is_open):
                return False
            try:
                ser.write(raw)
                ser.flush()
                return True
            except Exception as e:
                log.warning("[serial] write error: %s", e)
                with self._lock:
                    if self._ser is ser:
                        try:
                            self._ser.close()
                        except Exception:
                            pass
                        self._ser = None
        return False

    def _send_and_wait(self, line, prefix="STATUS:", timeout=10):
        if not SERIAL_AVAILABLE:
            return False, "pyserial not installed"
        deadline = time.time() + 8
        while time.time() < deadline:
            with self._lock:
                if self._ser and self._ser.is_open:
                    break
            time.sleep(0.3)
        else:
            return False, "not connected"

        with self._lock:
            ser = self._ser
        if not (ser and ser.is_open):
            return False, "lost connection"

        with self._write_lock:
            if not (ser and ser.is_open):
                return False, "lost connection"
            try:
                ser.reset_input_buffer()
                ser.write((line + "\n").encode("utf-8"))
                ser.flush()
            except Exception as e:
                return False, str(e)

        while not self._rx_q.empty():
            try:
                self._rx_q.get_nowait()
            except queue.Empty:
                break
        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                resp = self._rx_q.get(timeout=min(0.2, deadline - time.time()))
                if resp.startswith(prefix):
                    return "OK" in resp, resp
            except queue.Empty:
                pass
        return False, f"timeout after {timeout}s"

    def _reader(self):
        while True:
            ser = None
            with self._lock:
                if self._ser and self._ser.is_open:
                    ser = self._ser
            if not ser:
                time.sleep(0.05)
                continue

            line = None
            try:
                ser.timeout = 0.1
                raw = ser.readline()
                if raw:
                    line = raw.decode("utf-8", errors="ignore").strip()
            except serial.SerialTimeoutException:
                # Transient read timeout — no data within 0.1s; not a fatal error
                continue
            except Exception:
                with self._lock:
                    if self._ser is ser:
                        try:
                            self._ser.close()
                        except Exception:
                            pass
                        self._ser = None
                time.sleep(0.05)
                continue

            if line:
                try:
                    self._dispatch_q.put_nowait(line)
                except queue.Full:
                    if time.time() - self._last_drop_warn > 5:
                        self._last_drop_warn = time.time()
                        log.warning("Dispatch queue full — dropping serial line")
                try:
                    self._rx_q.put_nowait(line)
                except queue.Full:
                    pass

    def _dispatcher(self):
        while not self._dispatch_stop.is_set():
            try:
                line = self._dispatch_q.get(timeout=0.5)
            except queue.Empty:
                continue
            for cb in list(self._line_callbacks):
                try:
                    cb(line)
                except Exception:
                    log.exception("Serial callback failed")

    def _keepalive(self):
        _min_reconnect = 0.0
        while True:
            time.sleep(3)
            ser = None
            with self._lock:
                if self._ser and self._ser.is_open:
                    ser = self._ser
            if ser:
                try:
                    present = {p.device for p in serial.tools.list_ports.comports()}
                    if ser.port in present:
                        continue
                except Exception:
                    continue
                with self._lock:
                    if self._ser is ser:
                        try:
                            self._ser.close()
                        except Exception:
                            pass
                        self._ser = None
            if time.time() < _min_reconnect:
                continue
            port = self._forced_port or self._find_matrix_port()
            if not port:
                continue
            try:
                new_ser = serial.Serial(port, 115200, timeout=1, dsrdtr=False, rtscts=False)
                new_ser.dtr = False
                new_ser.rts = False
                with self._lock:
                    self._ser = new_ser
                log.info(f"[serial] connected to {port}")
            except Exception as e:
                log.debug(f"[serial] connect failed {port}: {e}")
                continue
            if self._ser and self._ser.is_open:
                time.sleep(3)
                with self._lock:
                    queue = dict(self._on_connect_queue)
                if self.connected_port() is None:
                    _min_reconnect = time.time() + 8.0
                    continue
                for key, value in queue.items():
                    self._write(f"SET:{key}={value}\n")
                self._write(f"SET:utc_offset={_local_utc_offset()}\n")
                self._write(f"SET:time={int(time.time())}\n")
                self._last_time_sync = time.time()
                log.info("[serial] settings + time pushed on connect")
                if not self._profile_checked:
                    self._profile_checked = True
                    try:
                        hw = self.detect_hardware(timeout=2)
                        if hw:
                            self._profile = profile_for(hw)
                            log.info("[serial] device profile: %s (hw=%s)",
                                     self._profile.id, hw)
                    except Exception:
                        log.debug("[serial] hardware detect failed", exc_info=True)

    def _time_sync_loop(self):
        while True:
            time.sleep(self._time_sync_interval)
            if self.connected_port() and time.time() - self._last_time_sync >= self._time_sync_interval * 0.9:
                self._write(f"SET:utc_offset={_local_utc_offset()}\n")
                self._write(f"SET:time={int(time.time())}\n")
                self._last_time_sync = time.time()

    @staticmethod
    def _find_matrix_port():
        if not SERIAL_AVAILABLE:
            return None
        for p in serial.tools.list_ports.comports():
            if getattr(p, "vid", None) in ESP32_VIDS:
                return p.device
        return None


serial_sender = SerialSender()
