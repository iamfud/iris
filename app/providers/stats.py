"""PC stats provider — CPU/GPU temp from MSI Afterburner, FPS from RTSS."""

import ctypes
import logging
import math
import struct
import threading
import time
from collections import namedtuple

import pystray

log = logging.getLogger("iris.stats")

Snapshot = namedtuple("Snapshot", "cpu_temp gpu_temp fps exe cpu_pct")


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
            if not math.isfinite(val):
                continue
            if "cpu" in name and "temp" in name:
                result.setdefault("cpu_temp", val)
            elif "gpu" in name and "temp" in name:
                result.setdefault("gpu_temp", val)
        return result or None


class StatsProvider:
    def __init__(self, cfg, serial_sender=None):
        self.cfg = cfg
        self.serial = serial_sender
        self._rtss = _RtssReader()
        self._mahm = _MahmReader()
        self._running = False
        self._manual_override = False
        self._snapshot = Snapshot(None, None, None, "", 0.0)
        self._lock = threading.Lock()

    def start(self):
        self._running = True
        if self.serial:
            self.serial.queue_on_connect("cpu_temp_lim", str(self.cfg.get("cpu_temp_lim", 90)))
            self.serial.queue_on_connect("gpu_temp_lim", str(self.cfg.get("gpu_temp_lim", 90)))
            self.serial.queue_on_connect("temp_alert", "1")
            if not self.cfg.get("pc_stats_enabled", False):
                self.serial.set_live("pc_disp", "0")
                self.serial.queue_on_connect("pc_disp", "0")
        threading.Thread(target=self._loop, daemon=True, name="stats-provider").start()


    def set_manual_override(self, enabled: bool):
        self._manual_override = enabled

    def stop(self):
        self._running = False

    def snapshot(self):
        with self._lock:
            return self._snapshot

    def _push_stats(self, cpu, cpu_temp, gpu_temp, fps):
        if not self.serial:
            return
        c = f"{cpu:.0f}"
        t = f"{cpu_temp:.0f}" if cpu_temp is not None else "-"
        g = f"{gpu_temp:.0f}" if gpu_temp is not None else "-"
        f = f"{min(fps, 999):.0f}" if fps is not None else "-"
        self.serial.send_stats(cpu, cpu_temp, gpu_temp, fps)

    def _loop(self):
        last_temp_poll = 0.0
        last_push = 0.0
        temp_interval = 5.0
        push_interval = 2.0
        pc_flags = self.cfg.get("pc_disp", 7)
        cpu_lim = self.cfg.get("cpu_temp_lim", 90)
        gpu_lim = self.cfg.get("gpu_temp_lim", 90)
        _temp_cooldown_s = 30
        overlay_active = False
        temp_alert_active = False
        cooldown_until = 0.0

        while self._running:
            fps_data = None
            try:
                fps_data = self._rtss.read()
            except Exception:
                pass

            now = time.time()
            if fps_data is None and int(now) % 30 == 0:
                log.info("RTSS poll: no FPS data (RTSS not hooked or not running?)")
            elif fps_data is not None and int(now) % 30 == 0:
                log.info("RTSS poll: FPS=%.0f app=%s", fps_data[0], fps_data[1])

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
                    cpu_temp = mahm.get("cpu_temp")
                    gpu_temp = mahm.get("gpu_temp")

            cpu_pct = 0.0
            try:
                import psutil
                cpu_pct = psutil.cpu_percent(interval=None)
            except Exception:
                pass

            with self._lock:
                self._snapshot = Snapshot(cpu_temp, gpu_temp, fps, exe, cpu_pct)

            game_active = fps is not None
            over_limit = (cpu_temp is not None and cpu_temp >= cpu_lim) or \
                         (gpu_temp is not None and gpu_temp >= gpu_lim)

            if over_limit:
                temp_alert_active = True
                cooldown_until = now + _temp_cooldown_s
            elif temp_alert_active and now >= cooldown_until:
                temp_alert_active = False

            should_show = self._manual_override or (self.cfg.get("pc_stats_enabled", False) and (game_active or temp_alert_active))

            if should_show and now - last_push >= push_interval:
                last_push = now
                if not overlay_active:
                    log.info("PC stats overlay activated (game=%s temp_alert=%s)",
                             game_active, temp_alert_active)
                    overlay_active = True
                if pc_flags and self.serial:
                    self.serial.set_live("pc_disp", str(pc_flags))
                self._push_stats(cpu_pct, cpu_temp, gpu_temp, fps)
            elif overlay_active and not should_show:
                overlay_active = False
                log.info("PC stats overlay deactivated (game=%s temp_alert=%s)",
                         game_active, temp_alert_active)
                if self.serial:
                    self.serial.set_live("pc_disp", "0")

            time.sleep(1.0)

    def menu_items(self):
        with self._lock:
            s = self._snapshot
        fps_str = f"{s.fps:.0f}" if s.fps is not None else "--"
        cpu_str = f"{s.cpu_temp:.0f}" if s.cpu_temp is not None else "--"
        gpu_str = f"{s.gpu_temp:.0f}" if s.gpu_temp is not None else "--"
        label = f"CPU: {cpu_str}°C  GPU: {gpu_str}°C  FPS: {fps_str}"
        if s.exe:
            label += f"  [{s.exe}]"
        return [pystray.MenuItem(label, None, enabled=False)]
