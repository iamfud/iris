"""Display priority ladder for the hardware display.

Plugin authors (and core providers) tag their display writes with a
priority.  Higher wins.  The ladder is device-agnostic; the firmware
render order and timings come from the active device profile
(``device_profile``).  Intent arbitration lives in ``display_manager``.

Levels (highest first):
  core notifications   — Iris core (Windows notification mirror, media)
  plugin alerts        — 4-letter high-priority alerts
  plugin notifications — plugin edge messages (scroll / sticky)
  persistent reminder  — progress claims that re-fire on an interval
  persistent urgent    — progress-bar claims that must win
  persistent normal    — default progress-bar claims
  persistent minor     — low-key progress-bar claims
  pc stats             — background PC telemetry (lowest)
"""

PRIO_CORE_NOTIFY = 900
PRIO_PLUGIN_ALERT = 800
PRIO_PLUGIN_NOTIFY = 700
PRIO_PERSIST_REMINDER = 650
PRIO_PERSIST_URGENT = 600
PRIO_PERSIST_NORMAL = 500
PRIO_PERSIST_MINOR = 400
PRIO_PC_STATS = 100

# Fallback timeouts — the active device profile is the source of truth.
NOTIFY_WINDOW_S = 8.0
PROGRESS_TIMEOUT_S = 5.0
