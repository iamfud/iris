"""PC Stats plugin — CPU/GPU temp from MSI Afterburner, FPS from RTSS."""

import ctypes
import logging
import math
import os
import struct
import threading
import time
from collections import namedtuple

from plugins.pc_stats.connector import PCStatsConnector

log = logging.getLogger("iris.plugins.pc_stats")

Snapshot = namedtuple("Snapshot", "cpu_temp gpu_temp fps exe cpu_pct refresh_rate")


class _RtssReader:
    _MAP = "RTSSSharedMemoryV2"
    _READ = 0x0004
    _SIG = 0x52545353
    _E_NAME = 4
    _E_TIME0 = 268
    _E_TIME1 = 272
    _E_FRAMES = 276
    _E_FPS = 812
    _H_ENTRY_SZ = 8
    _H_ARR_OFF = 12
    _H_ARR_CNT = 16

    def __init__(self):
        k = ctypes.windll.kernel32
        k.OpenFileMappingW.restype = ctypes.c_void_p
        k.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
        k.MapViewOfFile.restype = ctypes.c_void_p
        k.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]
        k.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.OpenProcess.restype = ctypes.c_void_p
        k.OpenProcess.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
        k.GetExitCodeProcess.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
        k.GetTickCount.restype = ctypes.c_uint32
        self._k = k

    def running(self):
        h = self._k.OpenFileMappingW(self._READ, False, self._MAP)
        if not h:
            return False
        self._k.CloseHandle(h)
        return True

    def read(self):
        h = self._k.OpenFileMappingW(self._READ, False, self._MAP)
        if not h:
            return None
        try:
            base = self._k.MapViewOfFile(h, self._READ, 0, 0, 0)
            if not base:
                return None
            try:
                return self._parse(base)
            finally:
                self._k.UnmapViewOfFile(base)
        finally:
            self._k.CloseHandle(h)

    def _parse(self, base):
        if ctypes.string_at(base, 4) != self._SIG.to_bytes(4, "little"):
            return None
        entry_sz = int.from_bytes(ctypes.string_at(base + self._H_ENTRY_SZ, 4), "little")
        arr_off = int.from_bytes(ctypes.string_at(base + self._H_ARR_OFF, 4), "little")
        arr_cnt = int.from_bytes(ctypes.string_at(base + self._H_ARR_CNT, 4), "little")
        if not entry_sz or not arr_cnt:
            return None
        now_ms = self._k.GetTickCount()
        best_fps, best_name = 0.0, ""
        for i in range(min(arr_cnt, 128)):
            e = base + arr_off + i * entry_sz
            name = ctypes.string_at(e + self._E_NAME, 260).split(b"\x00")[0].decode("utf-8", errors="ignore")
            if not name:
                continue
            time1 = int.from_bytes(ctypes.string_at(e + self._E_TIME1, 4), "little")
            age = (now_ms - time1) & 0xFFFFFFFF
            if age > 3000:
                continue
            fps = 0.0
            if entry_sz > self._E_FPS + 4:
                fps_raw = int.from_bytes(ctypes.string_at(e + self._E_FPS, 4), "little")
                if fps_raw:
                    fps = fps_raw / 1000.0
            if not fps and entry_sz > self._E_FRAMES + 4:
                frames = int.from_bytes(ctypes.string_at(e + self._E_FRAMES, 4), "little")
                time0 = int.from_bytes(ctypes.string_at(e + self._E_TIME0, 4), "little")
                dt = time1 - time0
                if frames > 0 and dt > 0:
                    fps = frames * 1000.0 / dt
            if fps > best_fps:
                best_fps = fps
                best_name = name
        if best_fps <= 0:
            return None
        return best_fps, best_name


class _MahmReader:
    _MAP = "MAHMSharedMemory"
    _READ = 0x0004
    _SIG = 0x4D41484D
    _H_HDR_SZ = 8
    _H_SRC_CNT = 12
    _H_SRC_SZ = 16
    _S_NAME = 0
    _S_DATA = 1300

    def __init__(self):
        k = ctypes.windll.kernel32
        k.OpenFileMappingW.restype = ctypes.c_void_p
        k.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
        k.MapViewOfFile.restype = ctypes.c_void_p
        k.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]
        k.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        self._k = k

    def running(self):
        h = self._k.OpenFileMappingW(self._READ, False, self._MAP)
        if not h:
            return False
        self._k.CloseHandle(h)
        return True

    def read(self):
        h = self._k.OpenFileMappingW(self._READ, False, self._MAP)
        if not h:
            return None
        try:
            base = self._k.MapViewOfFile(h, self._READ, 0, 0, 0)
            if not base:
                return None
            try:
                return self._parse(base)
            finally:
                self._k.UnmapViewOfFile(base)
        finally:
            self._k.CloseHandle(h)

    def _parse(self, base):
        sig = int.from_bytes(ctypes.string_at(base, 4), "little")
        if sig != self._SIG:
            return None
        hdr_sz = int.from_bytes(ctypes.string_at(base + self._H_HDR_SZ, 4), "little")
        src_cnt = int.from_bytes(ctypes.string_at(base + self._H_SRC_CNT, 4), "little")
        src_sz = int.from_bytes(ctypes.string_at(base + self._H_SRC_SZ, 4), "little")
        if not src_sz or not src_cnt:
            return None
        src_base = base + hdr_sz
        result = {}
        for i in range(min(src_cnt, 256)):
            e = src_base + i * src_sz
            name = ctypes.string_at(e + self._S_NAME, 260).split(b"\x00")[0].decode("utf-8", errors="ignore").lower()
            val = struct.unpack("<f", ctypes.string_at(e + self._S_DATA, 4))[0]
            if not math.isfinite(val) or val <= 0:
                continue
            if "cpu" in name and ("temp" in name or "tctl" in name or "package" in name or "core" in name):
                result.setdefault("cpu_temp", val)
            elif ("gpu" in name or "graphics" in name or "vga" in name) and "temp" in name:
                result.setdefault("gpu_temp", val)
        return result or None


class Plugin:
    name = "pc_stats"
    display_name = "PC Stats"

    def __init__(self, cfg, serial_sender=None, overlays=None):
        self._cfg = cfg
        self._serial = serial_sender
        self.overlays = overlays
        self._connector = PCStatsConnector(cfg, serial_sender)
        self._rtss = _RtssReader()
        self._mahm = _MahmReader()
        self._running = False
        self._snapshot = Snapshot(None, None, None, "", 0.0, 60)
        self._lock = threading.Lock()

    def _pcfg(self):
        return (self._cfg.get("plugins") or {}).get("pc_stats", {})

    @staticmethod
    def _to_f(c):
        return c * 9.0 / 5.0 + 32.0 if c is not None else None

    def start(self):
        self._connector.normalize_limits()
        self._connector.connect()
        self._running = True
        if self._serial:
            alarm_on = bool(self._pcfg().get("overheat_alarm", True))
            self._serial.queue_on_connect("temp_alert", "1" if alarm_on else "0")
            self._serial.set_live("pc_disp", "0")
            self._serial.queue_on_connect("pc_disp", "0")
        threading.Thread(target=self._loop, daemon=True, name="pc-stats-plugin").start()
        log.info("pc_stats plugin started")

    def stop(self):
        self._running = False
        self._connector.disconnect()

    def on_tap(self, control_id, value=None):
        self._connector.handle(control_id, value)

    def get_options(self, option_key):
        return self._connector.get_options(option_key)

    def poll(self):
        with self._lock:
            s = self._snapshot
        use_f = self._pcfg().get("use_fahrenheit", False)
        rr = int(s.refresh_rate) if s.refresh_rate else 60
        return {
            "available": True,
            "cpu_temp": self._to_f(s.cpu_temp) if use_f else s.cpu_temp,
            "gpu_temp": self._to_f(s.gpu_temp) if use_f else s.gpu_temp,
            "fps": s.fps,
            "fps_max": rr,
            "refresh_rate": rr,
            "exe": s.exe,
            "cpu_pct": s.cpu_pct,
            "cpu_temp_unit": "\u00b0F" if use_f else "\u00b0C",
            "cpu_temp_max": 212 if use_f else 100,
            "gpu_temp_unit": "\u00b0F" if use_f else "\u00b0C",
            "gpu_temp_max": 212 if use_f else 100,
        }

    def snapshot(self):
        with self._lock:
            s = self._snapshot
        d = self.poll()
        d["layout"] = [
            {
                "title": "Hardware Stats",
                "fields": [
                    {"key": "cpu_temp", "label": "CPU Temperature"},
                    {"key": "gpu_temp", "label": "GPU Temperature"},
                    {"key": "fps", "label": "FPS"},
                ],
            }
        ]
        return d

    @staticmethod
    def _foreground_exe():
        try:
            import os
            import psutil
            user32 = ctypes.windll.user32
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                try:
                    desk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
                    if desk:
                        user32.SetThreadDesktop(desk)
                        hwnd = user32.GetForegroundWindow()
                except Exception:
                    pass
            if not hwnd:
                return ""
            pid = ctypes.c_ulong()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            if not pid.value:
                return ""
            proc = psutil.Process(pid.value)
            return os.path.basename(proc.name()).lower().strip()
        except Exception:
            return ""

    def _push_stats(self, cpu, cpu_temp, gpu_temp, fps):
        if not self._serial:
            return
        if cpu_temp is not None or gpu_temp is not None or fps is not None:
            self._serial.send_stats(cpu, cpu_temp, gpu_temp, fps)

    def _loop(self):
        import overheat_alarm
        import psutil
        from win_platform import get_monitor_refresh_rate

        temp_interval = 2.0
        push_interval = 0.5
        refresh_interval = 60.0
        last_temp_poll = 0.0
        last_push = 0.0
        last_refresh_poll = 0.0
        refresh_rate = 60
        overlay_active = False
        temp_alert_active = False
        _temp_cooldown_s = 10.0
        cooldown_until = 0.0
        was_overheat = False

        while self._running:
            fps_data = None
            try:
                fps_data = self._rtss.read()
            except Exception:
                pass

            now = time.time()
            with self._lock:
                if fps_data:
                    fps, exe = fps_data
                else:
                    fps, exe = None, ""
                cpu_temp = self._snapshot.cpu_temp
                gpu_temp = self._snapshot.gpu_temp

            if now - last_temp_poll >= temp_interval:
                last_temp_poll = now
                mahm = None
                try:
                    mahm = self._mahm.read()
                except Exception:
                    pass
                if mahm:
                    if mahm.get("cpu_temp") is not None:
                        cpu_temp = mahm.get("cpu_temp")
                    if mahm.get("gpu_temp") is not None:
                        gpu_temp = mahm.get("gpu_temp")

            if now - last_refresh_poll >= refresh_interval:
                last_refresh_poll = now
                try:
                    refresh_rate = get_monitor_refresh_rate()
                except Exception:
                    pass

            cpu_pct = 0.0
            try:
                cpu_pct = psutil.cpu_percent(interval=None)
            except Exception:
                pass

            with self._lock:
                self._snapshot = Snapshot(cpu_temp, gpu_temp, fps, exe, cpu_pct, refresh_rate)

            rtss_name = os.path.basename(exe).lower().strip() if exe else ""
            fg_name = self._foreground_exe()
            game_active = bool(fps is not None and rtss_name and fg_name and fg_name == rtss_name)
            pcfg = self._pcfg()
            cpu_lim = pcfg.get("cpu_temp_lim", 90)
            gpu_lim = pcfg.get("gpu_temp_lim", 75)
            if pcfg.get("use_fahrenheit", False):
                cpu_t = self._to_f(cpu_temp)
                gpu_t = self._to_f(gpu_temp)
            else:
                cpu_t, gpu_t = cpu_temp, gpu_temp
            over_limit = (cpu_t is not None and cpu_t >= cpu_lim) or \
                         (gpu_t is not None and gpu_t >= gpu_lim)

            if over_limit and not was_overheat:
                overheat_alarm.fire(
                    self._serial,
                    self.overlays,
                    enabled=bool(pcfg.get("overheat_alarm", True)),
                )
            was_overheat = over_limit

            if over_limit:
                temp_alert_active = True
                cooldown_until = now + _temp_cooldown_s
            elif temp_alert_active and now >= cooldown_until:
                temp_alert_active = False

            manual_override = self._cfg.get("pc_stats_manual", False)
            stats_enabled = self._cfg.get("pc_stats_enabled", False)
            should_show = manual_override or (stats_enabled and (game_active or temp_alert_active))

            if should_show and now - last_push >= push_interval:
                last_push = now
                if not overlay_active:
                    log.info("PC stats overlay activated (game=%s temp_alert=%s)",
                             game_active, temp_alert_active)
                    overlay_active = True
                pc_flags = self._cfg.get("pc_disp", 7)
                if pc_flags and self._serial:
                    self._serial.set_live("pc_disp", str(pc_flags))
                self._push_stats(cpu_pct, cpu_temp, gpu_temp, fps)
            elif overlay_active and not should_show:
                overlay_active = False
                log.info("PC stats overlay deactivated (game=%s temp_alert=%s)",
                         game_active, temp_alert_active)
                if self._serial:
                    self._serial.set_live("pc_disp", "0")

            time.sleep(1.0)
