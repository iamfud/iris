"""Authentication, rate-limiting, and session validation helpers for Iris server."""

import hashlib
import json
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


def action_id_for_slot(slot):
    """Return a stable opaque identifier for a configured action slot."""
    if not isinstance(slot, dict):
        return ""
    def strip_ids(value):
        if isinstance(value, list):
            return [strip_ids(item) for item in value]
        if isinstance(value, dict):
            return {key: strip_ids(item) for key, item in value.items() if key != "action_id"}
        return value
    clean = strip_ids(slot)
    raw = json.dumps(clean, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return "a_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]


def _configured_slots(cfg):
    if not isinstance(cfg, dict):
        return
    for key in ("panel_board", "panel_utility", "panel_core"):
        for slot in cfg.get(key) or []:
            if isinstance(slot, dict):
                yield slot
    for profile in cfg.get("panel_profiles") or []:
        if not isinstance(profile, dict):
            continue
        for slot in profile.get("board") or []:
            if isinstance(slot, dict):
                yield slot


def resolve_action_slot(action_id, cfg):
    """Resolve an opaque action ID to the current server-side slot definition."""
    if not isinstance(action_id, str) or not action_id or not isinstance(cfg, dict):
        return None
    for builtin in (
        {"type": "SCREENSHOT", "entity": "system.screenshot"},
        {"type": "MEDIA_PREV"},
        {"type": "MEDIA_PLAY"},
        {"type": "MEDIA_NEXT"},
    ):
        if action_id_for_slot(builtin) == action_id:
            return builtin
    for slot in _configured_slots(cfg):
        if action_id_for_slot(slot) == action_id:
            return dict(slot)
    return None


def annotate_action_slots(value):
    """Copy a panel structure and attach server-derived action IDs to slots."""
    if isinstance(value, list):
        return [annotate_action_slots(item) for item in value]
    if not isinstance(value, dict):
        return value
    result = {key: annotate_action_slots(item) for key, item in value.items()}
    if result.get("type"):
        result["action_id"] = action_id_for_slot(result)
    return result


def is_authorized_slot(slot, cfg):
    """Compatibility wrapper for callers that still pass an annotated slot."""
    if not isinstance(slot, dict):
        return False
    return resolve_action_slot(slot.get("action_id"), cfg) is not None


_LAN_SAFE_CORE_ACTIONS = frozenset({"display", "overlay", "mic", "mic_mute", "lighting", "lighting_sync"})
_LAN_SAFE_TYPES = frozenset({"MEDIA_PREV", "MEDIA_PLAY", "MEDIA_NEXT", "AUDIO OUTPUT", "CORE"})


def resolve_mobile_action(action_id, cfg):
    """Resolve an action only from the active mobile deck and safe slot types."""
    if not isinstance(action_id, str) or not action_id or not isinstance(cfg, dict):
        return None
    from panel_actions import resolve_panel_board
    board, _, _ = resolve_panel_board(cfg)
    candidates = list(board) + list(cfg.get("panel_utility") or []) + list(cfg.get("panel_core") or [])
    for builtin in (
        {"type": "MEDIA_PREV"},
        {"type": "MEDIA_PLAY"},
        {"type": "MEDIA_NEXT"},
    ):
        candidates.append(builtin)
    for slot in candidates:
        if not isinstance(slot, dict) or action_id_for_slot(slot) != action_id:
            continue
        slot_type = str(slot.get("type") or "").upper()
        if slot_type not in _LAN_SAFE_TYPES:
            return None
        if slot_type == "CORE" and str(slot.get("core_action") or "").lower() not in _LAN_SAFE_CORE_ACTIONS:
            return None
        return dict(slot)
    return None
