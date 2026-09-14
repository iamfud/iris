"""Iris — Configuration."""

import json
import os
import sys
import threading
from constants import DEFAULT_CONFIG
import paths

_save_lock = threading.Lock()


def config_path():
    return paths.get_config_path()


def load_config():
    try:
        with open(config_path()) as f:
            raw = json.load(f)
        # Migrate old key names
        if "ha_board" in raw and "panel_board" not in raw:
            raw["panel_board"] = raw.pop("ha_board")
        # Legacy plaintext password keys were removed. panel_password_hash
        # (Argon2id PHC string) is kept — it is the active pairing password.
        for stale in ("panel_password", "panel_password_salt"):
            raw.pop(stale, None)
        # Migrate legacy openrgb plugin config to rgb umbrella plugin
        plugins_cfg = raw.get("plugins")
        if isinstance(plugins_cfg, dict):
            if "openrgb" in plugins_cfg and "rgb" not in plugins_cfg:
                plugins_cfg["rgb"] = plugins_cfg.pop("openrgb")
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
    with _save_lock:
        preserved = {}
        try:
            with open(path) as f:
                old = json.load(f)
            for key in old:
                if key not in cfg:
                    preserved[key] = old[key]
        except Exception:
            pass
        merged = {**DEFAULT_CONFIG, **preserved, **cfg}
        merged.pop("ha_board", None)  # remove stale old key
        tmp = path + ".tmp"
        try:
            with open(tmp, "w") as f:
                json.dump(merged, f, indent=2)
            os.replace(tmp, path)
            try:
                import plugin_manager
                plugin_manager.invalidate_plugin_discovery()
            except Exception:
                pass
        except Exception:
            try:
                os.unlink(tmp)
            except Exception:
                pass
