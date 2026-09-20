"""NVIDIA GPU telemetry via NVML (ctypes wrapper for nvml.dll)."""

import logging
from typing import Any, Dict

log = logging.getLogger("iris.telemetry.gpu")


class NvmlManager:
    """Gathers NVIDIA-specific telemetry via pynvml (ctypes wrapper for nvml.dll)."""

    def __init__(self):
        self.handle = None
        self.name = ""
        try:
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                from pynvml import (
                    nvmlInit, nvmlDeviceGetCount,
                    nvmlDeviceGetHandleByIndex, nvmlDeviceGetName
                )
                nvmlInit()
                if nvmlDeviceGetCount() > 0:
                    self.handle = nvmlDeviceGetHandleByIndex(0)
                    raw_name = nvmlDeviceGetName(self.handle)
                    self.name = raw_name.decode("utf-8") if isinstance(raw_name, bytes) else str(raw_name)
                    log.info("[telemetry.gpu] NVML detected GPU: %s", self.name)
        except Exception as ex:
            log.debug("[telemetry.gpu] NVML init unavailable: %s", ex)
            self.handle = None

    def read(self) -> Dict[str, Any]:
        if not self.handle:
            return {}
        try:
            from pynvml import (
                nvmlDeviceGetMemoryInfo, nvmlDeviceGetPowerUsage,
                nvmlDeviceGetEnforcedPowerLimit, nvmlDeviceGetFanSpeed,
                nvmlDeviceGetPerformanceState, nvmlDeviceGetTemperature,
                nvmlDeviceGetClockInfo, nvmlDeviceGetUtilizationRates,
                NVML_TEMPERATURE_GPU, NVML_CLOCK_GRAPHICS, NVML_CLOCK_MEM
            )
            h = self.handle
            mem = nvmlDeviceGetMemoryInfo(h)
            used_gb = round(mem.used / 1e9, 2)
            total_gb = round(mem.total / 1e9, 2)
            pct = round(100.0 * mem.used / mem.total, 1) if mem.total else 0.0

            try:
                temp_c = float(nvmlDeviceGetTemperature(h, NVML_TEMPERATURE_GPU))
            except Exception:
                temp_c = None

            try:
                gpu_clk = int(nvmlDeviceGetClockInfo(h, NVML_CLOCK_GRAPHICS))
            except Exception:
                gpu_clk = None

            try:
                mem_clk = int(nvmlDeviceGetClockInfo(h, NVML_CLOCK_MEM))
            except Exception:
                mem_clk = None

            try:
                util = nvmlDeviceGetUtilizationRates(h)
                gpu_util = int(util.gpu)
            except Exception:
                gpu_util = None

            try:
                power_w = round(nvmlDeviceGetPowerUsage(h) / 1000.0, 1)
            except Exception:
                power_w = None

            try:
                power_lim = round(nvmlDeviceGetEnforcedPowerLimit(h) / 1000.0, 1)
            except Exception:
                power_lim = None

            try:
                fan = nvmlDeviceGetFanSpeed(h)
            except Exception:
                fan = None

            try:
                pstate = "P" + str(nvmlDeviceGetPerformanceState(h))
            except Exception:
                pstate = None

            return {
                "gpu_temp": temp_c,
                "gpu_load": gpu_util,
                "gpu_core_mhz": gpu_clk,
                "gpu_mem_mhz": mem_clk,
                "vram_used": used_gb,
                "vram_total": total_gb,
                "vram_pct": pct,
                "power_w": power_w,
                "power_lim_w": power_lim,
                "fan_pct": fan,
                "pstate": pstate,
            }
        except Exception as ex:
            log.debug("[telemetry.gpu] NVML read error: %s", ex)
            return {}

    def close(self):
        try:
            from pynvml import nvmlShutdown
            nvmlShutdown()
        except Exception:
            pass
        self.handle = None
