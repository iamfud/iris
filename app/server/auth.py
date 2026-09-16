"""Authentication, rate-limiting, and session validation helpers for Iris server."""

import time
from server.devices import _DEVICES, token_hash, touch_device, save_devices

_LOGIN_FAILURES = {}  # ip -> (count, lockout_until)


def is_loopback_address(ip):
    """True for loopback source addresses (127.0.0.0/8 or ::1)."""
    try:
        if not ip:
            return False
        return ip == "::1" or ip.startswith("127.")
    except Exception:
        return False


def valid_session(tok):
    """True when tok is a valid paired-device session cookie."""
    if not tok:
        return False
    h = token_hash(tok)
    dex = _DEVICES.get(h)
    if dex is not None:
        exp = dex.get("exp") if isinstance(dex, dict) else dex
        if exp is None or time.time() > exp:
            _DEVICES.pop(h, None)
            save_devices()
            return False
        touch_device(h)
        return True
    return False


def check_auth_rate_limit(ip):
    """Return (allowed: bool, retry_after: int)."""
    now = time.time()
    record = _LOGIN_FAILURES.get(ip)
    if not record:
        return True, 0
    count, lockout_until = record
    if now < lockout_until:
        return False, max(1, int(lockout_until - now))
    if count >= 5 and now >= lockout_until:
        _LOGIN_FAILURES.pop(ip, None)
        return True, 0
    return True, 0


def record_auth_failure(ip):
    now = time.time()
    record = _LOGIN_FAILURES.get(ip, (0, 0))
    count = record[0] + 1
    lockout_until = record[1]
    if count >= 5:
        lockout_until = now + 60.0  # 60s lockout after 5 consecutive failures
    _LOGIN_FAILURES[ip] = (count, lockout_until)


def record_auth_success(ip):
    _LOGIN_FAILURES.pop(ip, None)


def is_authorized_slot(slot, cfg):
    """Verify that an action slot requested by a remote peer matches a pre-configured button."""
    if not isinstance(slot, dict) or not isinstance(cfg, dict):
        return False
    stype = str(slot.get("type") or "").strip()
    if not stype:
        return False

    # Safe built-in controls that only affect media transport or audio toggling
    if stype in ("MEDIA_PLAY", "MEDIA_NEXT", "MEDIA_PREV", "MEDIA_EJECT", "AUDIO OUTPUT", "EMPTY"):
        return True

    candidates = []
    candidates.extend(cfg.get("panel_board") or [])
    candidates.extend(cfg.get("panel_utility") or [])
    candidates.extend(cfg.get("panel_core") or [])
    for prof in cfg.get("panel_profiles") or []:
        if isinstance(prof, dict):
            candidates.extend(prof.get("board") or [])

    spath = str(slot.get("shortcut_path") or "").strip()
    sargs = str(slot.get("shortcut_args") or "").strip()
    saction = str(slot.get("core_action") or "").strip()
    sname = str(slot.get("name") or "").strip()

    for c in candidates:
        if not isinstance(c, dict):
            continue
        if str(c.get("type") or "").strip() != stype:
            continue
        if stype in ("SHORTCUT", "GROUP"):
            cpath = str(c.get("shortcut_path") or "").strip()
            cargs = str(c.get("shortcut_args") or "").strip()
            if cpath == spath and cargs == sargs:
                return True
        elif stype == "CORE":
            if str(c.get("core_action") or "").strip() == saction:
                return True
        elif stype == "MACRO":
            if sname and str(c.get("name") or "").strip() == sname:
                return True
        elif stype in ("TOGGLE", "HOTKEY", "ACTION", "SENSOR"):
            return True
    return False
