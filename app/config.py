"""Iris — Configuration."""

import json
import os
import sys
from constants import DEFAULT_CONFIG


def config_path():
    if getattr(sys, "frozen", False):
        base = os.path.join(os.environ["APPDATA"], "Iris")
        os.makedirs(base, exist_ok=True)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "iris_config.json")


def load_config():
    try:
        with open(config_path()) as f:
            raw = json.load(f)
        # Migrate old key names
        if "ha_board" in raw and "panel_board" not in raw:
            raw["panel_board"] = raw.pop("ha_board")
        # Password auth was removed (QR pairing is the only remote path).
        for stale in ("panel_password", "panel_password_salt",
                      "panel_password_hash"):
            raw.pop(stale, None)
        try:
            from panel_actions import ensure_panel_defaults
            ensure_panel_defaults(raw)
        except Exception:
            pass
        return {**DEFAULT_CONFIG, **raw}
    except Exception:
        return dict(DEFAULT_CONFIG)


def save_config(cfg):
    path = config_path()
    merged = {**DEFAULT_CONFIG, **cfg}
    merged.pop("ha_board", None)  # remove stale old key
    tmp = path + ".tmp"
    try:
        with open(tmp, "w") as f:
            json.dump(merged, f, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except Exception:
            pass
