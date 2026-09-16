"""CPU frequency, boost clock, and core metrics using Windows PDH."""

import logging
from typing import Any, List, Optional, Tuple

import psutil

log = logging.getLogger("iris.telemetry.cpu")


class CpuFreqTracker:
    """Tracks real-time active boost frequency (per-core peak & overall avg).

    Uses Windows Performance Data Helper (PDH) '\\Processor Information' counters,
    which read true hardware boost states without needing elevated/admin privileges.
    """

    def __init__(self):
        self.enabled = False
        self.query = None
        self.tot_counter = None
        self.core_counters: List[Any] = []
        self.base_mhz = self._detect_base_mhz()

        try:
            import win32pdh
            self._pdh = win32pdh
            self.query = win32pdh.OpenQuery()
            _, instances = win32pdh.EnumObjectItems(
                None, None, "Processor Information", win32pdh.PERF_DETAIL_WIZARD
            )
            for inst in instances:
                if not inst.endswith("_Total"):
                    try:
                        p = win32pdh.MakeCounterPath((None, "Processor Information", inst, None, -1, "% Processor Performance"))
                        c = win32pdh.AddCounter(self.query, p)
                        self.core_counters.append(c)
                    except Exception:
                        pass

            for tot_name in ("_Total", "0,_Total"):
                try:
                    p = win32pdh.MakeCounterPath((None, "Processor Information", tot_name, None, -1, "% Processor Performance"))
                    self.tot_counter = win32pdh.AddCounter(self.query, p)
                    break
                except Exception:
                    pass

            # Initial warm-up tick so subsequent reads have valid deltas
            win32pdh.CollectQueryData(self.query)
            self.enabled = True
        except Exception as ex:
            log.debug("[telemetry.cpu] PDH init failed (fallback to psutil): %s", ex)
            self.enabled = False
            self.close()

    def _detect_base_mhz(self) -> float:
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\CentralProcessor\0")
            mhz, _ = winreg.QueryValueEx(key, "~MHz")
            if mhz and float(mhz) > 0:
                return float(mhz)
        except Exception:
            pass

        try:
            f = psutil.cpu_freq()
            if f and f.current > 0:
                return float(f.current)
        except Exception:
            pass
        return 3400.0

    def read(self) -> Tuple[Optional[float], Optional[float]]:
        """Returns (peak_ghz, avg_ghz) or (None, None) if unavailable."""
        if not self.enabled or not self.query or not hasattr(self, "_pdh"):
            return None, None

        try:
            self._pdh.CollectQueryData(self.query)
            core_vals: List[float] = []
            for c in self.core_counters:
                try:
                    _, v = self._pdh.GetFormattedCounterValue(c, self._pdh.PDH_FMT_DOUBLE)
                    if v > 0:
                        core_vals.append(v)
                except Exception:
                    pass

            avg_pct = None
            if self.tot_counter:
                try:
                    _, tot_v = self._pdh.GetFormattedCounterValue(self.tot_counter, self._pdh.PDH_FMT_DOUBLE)
                    if tot_v > 0:
                        avg_pct = tot_v
                except Exception:
                    pass

            if not core_vals and avg_pct is None:
                return None, None

            peak_pct = max(core_vals) if core_vals else avg_pct
            if avg_pct is None:
                avg_pct = sum(core_vals) / len(core_vals)

            peak_ghz = round((peak_pct * self.base_mhz) / 100000.0, 2)
            avg_ghz = round((avg_pct * self.base_mhz) / 100000.0, 2)
            peak_ghz = max(peak_ghz, avg_ghz)
            return peak_ghz, avg_ghz
        except Exception as ex:
            log.debug("[telemetry.cpu] PDH read error: %s", ex)
            return None, None

    def close(self):
        if self.query and hasattr(self, "_pdh"):
            try:
                self._pdh.CloseQuery(self.query)
            except Exception:
                pass
            self.query = None
        self.core_counters.clear()
        self.tot_counter = None
        self.enabled = False
