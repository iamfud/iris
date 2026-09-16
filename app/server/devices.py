"""Devices registry and metadata for Iris web portal pairing."""

import hashlib
import json
import os
import re
import time

_DEVICE_TTL = 365 * 24 * 3600
_DEVICES = {}
_last_devices_save = 0.0


def devices_path():
    try:
        from config import config_path as _cp
        return os.path.join(os.path.dirname(_cp()), "devices.json")
    except Exception:
        return os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "devices.json")


def load_devices():
    try:
        with open(devices_path()) as f:
            data = json.load(f)
        if isinstance(data, dict):
            for k, v in data.items():
                if not isinstance(v, dict):
                    v = {"exp": v, "ua": "", "created": None, "last_seen": None}
                _DEVICES[k] = v
    except Exception:
        pass


def save_devices():
    try:
        with open(devices_path(), "w") as f:
            json.dump(_DEVICES, f, indent=2)
    except Exception:
        pass


def touch_device(tok_hash):
    """Refresh a device's last-seen timestamp (throttled disk writes)."""
    global _last_devices_save
    rec = _DEVICES.get(tok_hash)
    if not isinstance(rec, dict):
        return
    rec["last_seen"] = time.time()
    now = time.time()
    if now - _last_devices_save >= 30:
        _last_devices_save = now
        save_devices()


def ua_device_name(ua):
    """Best-effort friendly name derived from the device's User-Agent."""
    if not ua:
        return "Paired device"
    low = ua.lower()
    if "ipad" in low:
        return "iPad"
    if "iphone" in low:
        return "iPhone"
    if "android" in low:
        m = re.search(r";\s*([^;\s()/]+?)\s+Build/", ua)
        if m:
            return m.group(1).strip()
        return "Android device"
    if "macintosh" in low or "mac os" in low:
        return "Mac"
    if "windows" in low:
        return "Windows PC"
    if "linux" in low:
        return "Linux"
    if "pywebview" in low:
        return "Iris Panel"
    return "Connected device"


def get_devices():
    """Return non-sensitive metadata for every unexpired paired device."""
    now = time.time()
    out = []
    for h, rec in _DEVICES.items():
        exp = rec.get("exp") if isinstance(rec, dict) else rec
        if exp is None or now > exp:
            continue
        if isinstance(rec, dict):
            out.append({
                "id": h,
                "name": ua_device_name(rec.get("ua", "")),
                "ua": rec.get("ua", ""),
                "created": rec.get("created"),
                "last_seen": rec.get("last_seen"),
            })
        else:
            out.append({
                "id": h, "name": "Paired device", "ua": "",
                "created": None, "last_seen": None,
            })
    out.sort(key=lambda d: d.get("last_seen") or 0, reverse=True)
    return out


def token_hash(tok):
    return hashlib.sha256((tok or "").encode("utf-8")).hexdigest()


# Initialize device list on load
load_devices()
