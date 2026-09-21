# Current PC Telemetry Behaviour

This document records the current implementation before telemetry
consolidation. It is a baseline, not a proposed architecture.

## Primary snapshot

`app/telemetry/collector.py:TelemetryEngine.collect()` builds the central
snapshot.

| Value | Current source and precedence |
| --- | --- |
| CPU usage | `psutil.cpu_times()` delta. If the calculated value is `0.0` or unavailable and LHM reports `cpu_load`, LHM `cpu_load` replaces it. The snapshot publishes the same value as `cpu`, `cpu_usage`, and `cpu_pct`. |
| CPU temperature | LHM `cpu_temp`. If unavailable, the central collector does not use MAHM or NVML for CPU temperature; the value remains `None`. |
| GPU temperature | LHM `gpu_temps["GPU Core"]`; if that is `None`, NVML `gpu_temp` is used. |
| FPS | `FpsTracker.get_stats()["fps"]`. `FpsTracker` can use PresentMon and RTSS data according to its own selection and fallback logic. |

Missing temperature or FPS values remain `None` in the central snapshot.
CPU usage normally remains numeric because the collector retains its previous
CPU percentage and also has the LHM-load fallback.

## PC Stats cached path

`app/plugins/pc_stats/plugin.py` maintains a separate cached `Snapshot`.
Its background loop first consumes the central engine snapshot when an engine
exists:

- `cpu_pct`, CPU temperature, GPU temperature, FPS, clocks, VRAM, and power
  are copied from the engine snapshot;
- if either temperature is missing, MAHM shared memory is read and only the
  missing temperature is filled;
- the cached result is exposed by `Plugin.poll()`.

When the central engine is unavailable, the PC Stats loop instead:

- reads FPS and process name from RTSS shared memory;
- reads temperatures from MAHM shared memory on its temperature interval;
- reads CPU usage from `psutil.cpu_percent()`.

`Plugin.poll()` reports `"available": True` even when individual values are
`None`. It applies Fahrenheit conversion to CPU and GPU temperatures when
`use_fahrenheit` is enabled, and returns `°F`/212 limits; otherwise it returns
`°C`/100 limits. CPU usage and FPS are not converted.

## Entity consumers

`TelemetryEngine.get_entity_states()` formats the central snapshot into
`pc_stats.*` entity IDs:

- `pc_stats.cpu_usage`: percentage;
- `pc_stats.cpu_temp`: Celsius label;
- `pc_stats.gpu_temp`: Celsius label;
- `pc_stats.fps`: FPS label.

It omits an entity when that value is `None`.

`panel_entities.get_live_entity_states()` can differ from the engine result:

1. If `_app._stats_provider.last_stats` exists, its non-`None` PC values are
   inserted first.
2. `TelemetryEngine.get_entity_states()` only fills keys that are absent or
   currently have a `None` value.
3. Provider values can therefore take precedence over the current engine
   snapshot. These labels are always formatted as Celsius for temperatures.

## Gauge consumer

`panel_runtime._gauges()` has separate precedence:

1. It reads `TelemetryEngine.get_snapshot()`.
2. If CPU usage is missing, it falls back to `psutil.cpu_percent()`.
3. If an active `pc_stats` instance has a truthy `available` result, its
   non-`None` CPU usage, temperatures, and FPS override the engine values.
4. The PC Stats result can also override temperature units, limits, refresh
   rate, and FPS maximum.

Consequently, the panel gauge can differ from both
`TelemetryEngine.get_entity_states()` and `panel_entities` when PC Stats has
cached data or Fahrenheit mode is enabled.

## Known baseline ambiguities

- The central engine has no CPU-temperature fallback to MAHM; MAHM is applied
  in the PC Stats cached path.
- `panel_entities` and `panel_runtime` can select different sources because
  they use different precedence rules.
- Entity temperature labels remain Celsius even when the gauge path uses
  Fahrenheit through PC Stats.
- The engine CPU percentage uses `psutil.cpu_times()` deltas, while the
  no-engine PC Stats path uses `psutil.cpu_percent()`.
- FPS source selection is centralized in `FpsTracker` when the engine is
  active, but is RTSS-only in the no-engine PC Stats path.

These differences are captured by the baseline tests and must not be changed
without an explicit consolidation decision.
