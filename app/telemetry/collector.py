"""Central Telemetry Collector orchestrating CPU, GPU, RAM, Disk, Network, and Game metrics."""

import ctypes
import logging
import threading
import time
from typing import Any, Dict, Optional

import psutil

from telemetry.cpu import CpuFreqTracker
from telemetry.fps import FpsTracker
from telemetry.gpu import NvmlManager
from telemetry.lhm import LhmManager

log = logging.getLogger("iris.telemetry.collector")


def is_admin() -> bool:
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def format_uptime(boot_time: float) -> str:
    up_secs = max(0, int(time.time() - boot_time))
    h = up_secs // 3600
    m = (up_secs % 3600) // 60
    return f"{h}h {m:02d}m"


class TelemetryEngine:
    """Orchestrates hardware monitoring subsystems, background polling, and cached snapshots."""

    _instance: Optional["TelemetryEngine"] = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls) -> "TelemetryEngine":
        with cls._lock:
            if cls._instance is None:
                cls._instance = cls()
            return cls._instance

    def __init__(self):
        self._lhm = LhmManager()
        self._nvml = NvmlManager()
        self._fps_tracker = FpsTracker()
        self._cpu_tracker = CpuFreqTracker()

        self._net_prev = psutil.net_io_counters()
        self._net_t = time.time()
        self._boot_time = psutil.boot_time()
        self._gpu_name = self._nvml.name or "GPU"
        self._is_admin = is_admin()

        self._snapshot_lock = threading.Lock()
        self._last_snapshot: Dict[str, Any] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None

        psutil.cpu_percent(interval=None)  # warm-up

    def start(self, interval_sec: float = 1.0):
        if self._running:
            return
        self._running = True
        self._interval = interval_sec
        self._thread = threading.Thread(target=self._loop, daemon=True, name="telemetry-engine")
        self._thread.start()
        log.info("[telemetry] TelemetryEngine started (interval=%.1fs)", interval_sec)

    def stop(self):
        self._running = False
        self.close()

    def _loop(self):
        while self._running:
            try:
                snap = self.collect()
                with self._snapshot_lock:
                    self._last_snapshot = snap
            except Exception as ex:
                log.debug("[telemetry] Collect cycle error: %s", ex)
            time.sleep(self._interval)

    def get_snapshot(self) -> Dict[str, Any]:
        with self._snapshot_lock:
            if self._last_snapshot:
                return dict(self._last_snapshot)
        return self.collect()

    def collect(self) -> Dict[str, Any]:
        """Collect a complete snapshot of hardware telemetry."""
        # 1. CPU (psutil load & cores)
        cpu_pct = psutil.cpu_percent(interval=None)
        cores_str = f"{psutil.cpu_count(logical=False)}C / {psutil.cpu_count(logical=True)}T"

        # 2. System Memory & Storage (psutil)
        vm = psutil.virtual_memory()
        swap = psutil.swap_memory()
        try:
            disk_c = psutil.disk_usage("C:")
            disk_c_used = round(disk_c.used / 1e9, 1)
            disk_c_total = round(disk_c.total / 1e9, 1)
            disk_c_pct = disk_c.percent
        except Exception:
            disk_c_used, disk_c_total, disk_c_pct = 0, 0, 0

        # 3. Network bandwidth deltas
        now = time.time()
        net_now = psutil.net_io_counters()
        elapsed = max(0.001, now - self._net_t)
        net_up_mb = (net_now.bytes_sent - self._net_prev.bytes_sent) / elapsed / 1e6
        net_dn_mb = (net_now.bytes_recv - self._net_prev.bytes_recv) / elapsed / 1e6
        self._net_prev = net_now
        self._net_t = now

        # 4. LHM Readings
        lhm_data = self._lhm.read()
        gpu_temps = lhm_data.get("gpu_temps", {})
        gpu_clocks = lhm_data.get("gpu_clocks", {})
        gpu_loads = lhm_data.get("gpu_loads", {})

        gpu_core_temp = gpu_temps.get("GPU Core")
        gpu_hotspot = gpu_temps.get("GPU Hot Spot")
        gpu_mem_temp = gpu_temps.get("GPU Memory Junction")

        gpu_core_mhz = gpu_clocks.get("GPU Core")
        gpu_mem_mhz = gpu_clocks.get("GPU Memory")
        gpu_load = gpu_loads.get("GPU Core", lhm_data.get("gpu_load"))

        # 5. NVML Telemetry
        nvml_data = self._nvml.read()
        if gpu_core_temp is None:
            gpu_core_temp = nvml_data.get("gpu_temp")

        vram_used = nvml_data.get("vram_used")
        vram_total = nvml_data.get("vram_total")
        vram_pct = nvml_data.get("vram_pct")
        gpu_power = nvml_data.get("power_w") or lhm_data.get("gpu_power")
        gpu_power_lim = nvml_data.get("power_lim_w")
        gpu_fan = nvml_data.get("fan_pct")
        gpu_pstate = nvml_data.get("pstate")

        # 6. Game FPS & Title
        fps_stats = self._fps_tracker.get_stats()

        # 7. CPU Boost Frequency resolution
        peak_ghz, avg_ghz = self._cpu_tracker.read()
        base_mhz = self._cpu_tracker.base_mhz
        base_ghz = round(base_mhz / 1000.0, 2)

        # Fallback 1: LHM CPU Clocks if PDH was not available
        if peak_ghz is None and lhm_data.get("cpu_clocks"):
            clks = [v for v in lhm_data["cpu_clocks"].values() if v > 0]
            if clks:
                peak_ghz = round(max(clks) / 1000.0, 2)
                avg_ghz = round(sum(clks) / len(clks) / 1000.0, 2)

        # Fallback 2: psutil nominal frequency
        if peak_ghz is None:
            cpu_freq = psutil.cpu_freq()
            if cpu_freq and cpu_freq.current > 0:
                peak_ghz = round(cpu_freq.current / 1000.0, 2)
                avg_ghz = peak_ghz

        freq_str = f"{peak_ghz:.2f} GHz" if peak_ghz else ""
        ratio_str = f"{base_ghz:.2f} / {peak_ghz:.2f} GHz" if (base_ghz and peak_ghz) else ""

        # CPU package temperature
        cpu_temp = lhm_data.get("cpu_temp")

        snapshot = {
            # CPU
            "cpu": cpu_pct,
            "cpu_usage": cpu_pct,
            "cpu_freq": freq_str,
            "cpu_boost_peak": freq_str,
            "cpu_freq_avg": f"{avg_ghz:.2f} GHz" if avg_ghz else "",
            "cpu_base_freq": f"{base_ghz:.2f} GHz" if base_ghz else "",
            "cpu_clock_ratio": ratio_str,
            "cpu_cores": cores_str,
            "cpu_temp": cpu_temp,
            "cpu_vid": lhm_data.get("cpu_vid"),
            # GPU
            "gpu_pct": gpu_load if gpu_load is not None else 0,
            "gpu_usage": gpu_load if gpu_load is not None else 0,
            "gpu_temp": gpu_core_temp,
            "gpu_hotspot": gpu_hotspot,
            "gpu_mem_temp": gpu_mem_temp,
            "gpu_core_mhz": gpu_core_mhz,
            "gpu_mem_mhz": gpu_mem_mhz,
            "gpu_power": gpu_power,
            "gpu_power_lim": gpu_power_lim,
            "gpu_voltage": lhm_data.get("gpu_voltage"),
            "gpu_fan": gpu_fan,
            "gpu_pstate": gpu_pstate,
            "gpu_name": self._gpu_name,
            # VRAM
            "vram_used": vram_used,
            "vram_total": vram_total,
            "vram_pct": vram_pct if vram_pct is not None else 0,
            # System Memory
            "ram_pct": vm.percent,
            "ram_usage": vm.percent,
            "ram_used": round(vm.used / 1e9, 1),
            "ram_total": round(vm.total / 1e9, 1),
            "swap_pct": swap.percent,
            # Storage
            "disk_c_pct": disk_c_pct,
            "disk_c_used": disk_c_used,
            "disk_c_total": disk_c_total,
            # Network & System
            "net_up": round(net_up_mb, 2),
            "net_dn": round(net_dn_mb, 2),
            "procs": len(psutil.pids()),
            "uptime": format_uptime(self._boot_time),
            # Game FPS
            "fps": fps_stats.get("fps"),
            "fps_1pct_low": fps_stats.get("fps_1pct_low"),
            "frametime_ms": fps_stats.get("frametime_ms"),
            "game_name": fps_stats.get("game_name"),
            "is_admin": self._is_admin,
        }
        return snapshot

    def get_entity_states(self) -> Dict[str, Dict[str, Any]]:
        """Return formatted dictionary of entity states ready for panel_entities."""
        st = self.get_snapshot()
        states = {}
        if st.get("cpu_temp") is not None:
            states["pc_stats.cpu_temp"] = {"value": st["cpu_temp"], "label": f"{st['cpu_temp']}°C"}
        if st.get("gpu_temp") is not None:
            states["pc_stats.gpu_temp"] = {"value": st["gpu_temp"], "label": f"{st['gpu_temp']}°C"}
        if st.get("fps") is not None:
            states["pc_stats.fps"] = {"value": st["fps"], "label": f"{st['fps']} FPS"}
        if st.get("cpu_usage") is not None:
            states["pc_stats.cpu_usage"] = {"value": st["cpu_usage"], "label": f"{st['cpu_usage']}%"}
        if st.get("ram_usage") is not None:
            states["pc_stats.ram_usage"] = {"value": st["ram_usage"], "label": f"{st['ram_usage']}%"}
        if st.get("cpu_boost_peak"):
            states["pc_stats.cpu_freq"] = {"value": st["cpu_boost_peak"], "label": st["cpu_boost_peak"]}
        if st.get("vram_pct") is not None:
            states["pc_stats.vram_pct"] = {"value": st["vram_pct"], "label": f"{st['vram_pct']}%"}
        if st.get("game_name"):
            states["pc_stats.game_name"] = {"value": st["game_name"], "label": st["game_name"]}
        return states

    def close(self):
        if self._fps_tracker:
            self._fps_tracker.close()
        if self._cpu_tracker:
            self._cpu_tracker.close()
        if self._nvml:
            self._nvml.close()
        if self._lhm:
            self._lhm.close()
