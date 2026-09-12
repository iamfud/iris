"""Shared overheat alarm — fires exactly once per cooldown window.

The firmware path (``main.py`` on ``OVERHEAT:active``) and the PC-side check
(``pc_stats`` plugin, which runs even without the matrix device) can both
detect a temperature over-limit within the same second.  Both delegate here
so exactly one coin sound, one on-screen alert, and one phone red toast is
emitted per cooldown window.
"""

import logging
import threading
import time

log = logging.getLogger("iris.overheat")

_ALARM_COOLDOWN_S = 60.0

TITLE = "Overheat Warning"
MESSAGE = "CPU or GPU temperature over limit"
KEY = "overheat.alert"
ACCENT = "#ff5566"

_last_alarm = 0.0
_lock = threading.Lock()


def fire(serial_sender, overlays, enabled=True):
    """Raise the overheat alarm, deduplicated across trigger sources.

    Args:
        serial_sender: SerialComm (or None). Used for the phone red alert.
        overlays: OverlayService (or None). Used for the on-screen alert.
        enabled: overheat_alarm toggle; when falsy nothing fires.

    Returns:
        True if the alarm actually fired this time (and was not suppressed).
    """
    global _last_alarm
    if not enabled:
        log.info("[overheat] OVERHEAT — alarm disabled (overheat_alarm=False)")
        return False

    now = time.monotonic()
    with _lock:
        if now - _last_alarm < _ALARM_COOLDOWN_S:
            log.info("[overheat] OVERHEAT — alarm fired recently, skipping duplicate")
            return False
        _last_alarm = now

    try:
        import alarm_sound
        alarm_sound.play("coin")
        log.info("[overheat] OVERHEAT — playing coin")
    except Exception as e:
        log.warning("[overheat] sound failed: %s", e)

    if serial_sender is not None:
        try:
            serial_sender.send_alert(TITLE, MESSAGE, key=KEY)
        except Exception as e:
            log.warning("[overheat] send_alert failed: %s", e)

    if overlays is not None:
        try:
            from datetime import datetime as _dt
            overlays.hero(
                title=TITLE,
                subtitle=MESSAGE,
                fields=[("Status", "ALERT"), ("Time", _dt.now().strftime("%H:%M"))],
                accent=ACCENT,
                duration=6,
            )
        except Exception as e:
            log.warning("[overheat] on-screen alert failed: %s", e)

    return True