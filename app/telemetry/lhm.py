"""LibreHardwareMonitorLib wrapper via pythonnet/clr for CPU/GPU/Motherboard hardware sensors."""

import logging
import os
from typing import Any, Dict

from telemetry.paths import get_lhm_dll_path

log = logging.getLogger("iris.telemetry.lhm")


class LhmManager:
    """Wraps LibreHardwareMonitorLib.dll via pythonnet."""

    def __init__(self):
        self.computer = None
        self.enabled = False
        dll_path = get_lhm_dll_path()
        if not os.path.isfile(dll_path):
            log.debug("[telemetry.lhm] LibreHardwareMonitorLib.dll not found at %s", dll_path)
            return

        try:
            import pythonnet
            try:
                pythonnet.load("coreclr")
            except Exception:
                pass  # runtime may already be loaded

            import clr
            clr.AddReference(dll_path)

            from LibreHardwareMonitor.Hardware import Computer
            c = Computer()
            c.IsCpuEnabled = True
            c.IsGpuEnabled = True
            c.IsMemoryEnabled = True
            c.IsMotherboardEnabled = True
            c.Open()
            self.computer = c
            self.enabled = True
            log.info("[telemetry.lhm] LibreHardwareMonitorLib initialized successfully")
        except Exception as err:
            log.debug("[telemetry.lhm] LHM init failed: %s", err)
            self.enabled = False
            self.computer = None

    def read(self) -> Dict[str, Any]:
        data: Dict[str, Any] = {
            "cpu_temp": None,
            "cpu_load": None,
            "cpu_vid": None,
            "cpu_clocks": {},
            "gpu_temps": {},
            "gpu_clocks": {},
            "gpu_loads": {},
            "gpu_power": None,
            "gpu_voltage": None,
            "gpu_pcie_rx": None,
            "gpu_pcie_tx": None,
        }
        if not self.enabled or self.computer is None:
            return data

        try:
            for hw in self.computer.Hardware:
                hw.Update()
                ht = str(hw.HardwareType)
                if "Cpu" in ht:
                    for s in hw.Sensors:
                        if s.Value is None:
                            continue
                        stype, sname, val = str(s.SensorType), str(s.Name), float(s.Value)
                        if stype == "Temperature" and val > 0:
                            if data["cpu_temp"] is None or "Tctl" in sname or "Package" in sname:
                                data["cpu_temp"] = round(val, 1)
                        elif stype == "Load" and "Total" in sname:
                            data["cpu_load"] = round(val, 1)
                        elif stype == "Voltage" and "VID" in sname and data["cpu_vid"] is None:
                            data["cpu_vid"] = round(val, 2)
                        elif stype == "Clock" and val > 0:
                            data["cpu_clocks"][sname] = round(val, 1)
                    for sub in hw.SubHardware:
                        sub.Update()
                        for s in sub.Sensors:
                            if s.Value is not None and str(s.SensorType) == "Temperature" and float(s.Value) > 0:
                                data["cpu_temp"] = round(float(s.Value), 1)

                elif "Gpu" in ht:
                    for s in hw.Sensors:
                        if s.Value is None:
                            continue
                        stype, sname, val = str(s.SensorType), str(s.Name), float(s.Value)
                        if stype == "Temperature":
                            data["gpu_temps"][sname] = round(val, 1)
                        elif stype == "Clock":
                            data["gpu_clocks"][sname] = int(val)
                        elif stype == "Load":
                            data["gpu_loads"][sname] = round(val, 1)
                        elif stype == "Power" and ("Package" in sname or "GPU" in sname):
                            data["gpu_power"] = round(val, 1)
                        elif stype == "Voltage" and "Core" in sname:
                            data["gpu_voltage"] = round(val, 2)
                        elif stype == "Throughput":
                            if "Rx" in sname:
                                data["gpu_pcie_rx"] = val
                            elif "Tx" in sname:
                                data["gpu_pcie_tx"] = val
        except Exception as ex:
            log.debug("[telemetry.lhm] LHM read error: %s", ex)

        return data

    def close(self):
        if self.computer:
            try:
                self.computer.Close()
            except Exception:
                pass
            self.computer = None
