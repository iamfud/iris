"""Iris Telemetry Subsystem.

Provides high-performance, standalone PC hardware and gaming telemetry:
- CPU frequency & boost clocks via Windows PDH
- NVIDIA GPU telemetry via NVML
- Game FPS & frametimes via PresentMon ETW / RTSS
- CPU/GPU/Motherboard temperatures via LibreHardwareMonitor
- RAM, Storage, Network, and OS metrics
"""

from telemetry.collector import TelemetryEngine


def get_telemetry_engine() -> TelemetryEngine:
    """Return the singleton TelemetryEngine instance."""
    return TelemetryEngine.get_instance()


__all__ = ["TelemetryEngine", "get_telemetry_engine"]
