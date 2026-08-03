"""Device capability profiles.

The arbiter's timing and encoding parameters are device-specific.  The
matrix firmware (d1mini/MAX7219) auto-hides the progress bar 5s after
its last update, renders short notifications for 5s and scrolling ones
for 8s, and draws text layers above PROG.  Future devices with different
firmwares plug in here instead of hardcoding matrix timings into the
arbiter.

Profiles are keyed by the hardware id returned by ``IDENT?`` (e.g.
``d1mini_max7219_4``); the matrix is the default when no id is known.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class DeviceProfile:
    id: str = "d1mini_max7219"
    # Display geometry (px).
    width_px: int = 32
    height_px: int = 8
    # Progress bar (PROG:) behaviour.
    has_progress: bool = True
    progress_timeout_ms: int = 5000   # firmware auto-hide after last update
    progress_settle_len: int = 7      # letters shown once a long name scrolls
    progress_name_max_full: int = 40  # max label length the PC may send
    # Notifications (NOTIFY:) behaviour.
    text_step_ms: int = 35            # per-pixel scroll step
    notify_static_ms: int = 5000      # duration when text fits on screen
    notify_window_ms: int = 8000      # minimum duration when text scrolls
    # True when firmware layers text above progress (independent channels).
    notify_over_progress: bool = True
    layers_text_and_progress: bool = True
    # Alert (ALERT: / 4-letter bold).
    has_alert: bool = True
    alert_max_chars: int = 4
    alert_max_hold_ms: int = 60000
    alert_blink_ms: int = 500
    # Sticky (scroll once then hold).
    has_sticky: bool = True
    sticky_settle_len: int = 7
    sticky_max_hold_ms: int = 120000


MATRIX = DeviceProfile()

PROFILES = {
    "d1mini_max7219": MATRIX,
    "d1mini_max7219_4": MATRIX,
}


def profile_for(hw_id):
    if not hw_id:
        return MATRIX
    key = str(hw_id).strip().lower()
    return PROFILES.get(key, MATRIX)
