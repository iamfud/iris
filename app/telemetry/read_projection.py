"""Canonical read-only projection for the existing PC telemetry paths."""

from __future__ import annotations

from typing import Any, Dict, Mapping, Optional


def _first_value(snapshot: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        value = snapshot.get(key)
        if value is not None:
            return value
    return None


def project_pc_telemetry(
    engine_snapshot: Mapping[str, Any],
    *,
    pc_stats_snapshot: Optional[Mapping[str, Any]] = None,
    cpu_usage_fallback: Any = None,
) -> Dict[str, Any]:
    """Project existing read results without collecting or polling anything.

    ``pc_stats_snapshot`` must be an already-cached result. This helper never
    calls a plugin, reads hardware, or applies a new fallback source.
    """
    engine = engine_snapshot or {}
    values = {
        "cpu_usage": _first_value(engine, "cpu_pct", "cpu_usage", "cpu"),
        "cpu_temp": engine.get("cpu_temp"),
        "gpu_temp": engine.get("gpu_temp"),
        "fps": engine.get("fps"),
    }
    if values["cpu_usage"] is None and cpu_usage_fallback is not None:
        values["cpu_usage"] = cpu_usage_fallback

    gauges = {
        "cpu_pct": values["cpu_usage"],
        "cpu_temp": values["cpu_temp"],
        "gpu_temp": values["gpu_temp"],
        "fps": values["fps"],
        "cpu_temp_unit": "°C",
        "gpu_temp_unit": "°C",
        "cpu_temp_max": 100,
        "gpu_temp_max": 100,
    }

    pc_stats = pc_stats_snapshot or {}
    if pc_stats.get("available"):
        if pc_stats.get("cpu_pct") is not None:
            values["cpu_usage"] = pc_stats["cpu_pct"]
        if pc_stats.get("cpu_temp") is not None:
            values["cpu_temp"] = pc_stats["cpu_temp"]
        if pc_stats.get("gpu_temp") is not None:
            values["gpu_temp"] = pc_stats["gpu_temp"]
        if pc_stats.get("fps") is not None:
            values["fps"] = pc_stats["fps"]
        for key in (
            "cpu_temp_unit",
            "gpu_temp_unit",
            "cpu_temp_max",
            "gpu_temp_max",
        ):
            if pc_stats.get(key):
                gauges[key] = pc_stats[key]

    gauges.update(
        {
            "cpu_pct": values["cpu_usage"],
            "cpu_temp": values["cpu_temp"],
            "gpu_temp": values["gpu_temp"],
            "fps": values["fps"],
        }
    )

    entities = {}
    if values["cpu_temp"] is not None:
        entities["pc_stats.cpu_temp"] = {
            "value": values["cpu_temp"],
            "label": f"{values['cpu_temp']}°C",
        }
    if values["gpu_temp"] is not None:
        entities["pc_stats.gpu_temp"] = {
            "value": values["gpu_temp"],
            "label": f"{values['gpu_temp']}°C",
        }
    if values["fps"] is not None:
        entities["pc_stats.fps"] = {
            "value": values["fps"],
            "label": f"{values['fps']} FPS",
        }
    if values["cpu_usage"] is not None:
        entities["pc_stats.cpu_usage"] = {
            "value": values["cpu_usage"],
            "label": f"{values['cpu_usage']}%",
        }

    return {"gauges": gauges, "entities": entities}
