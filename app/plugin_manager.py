"""Plugin manager — discover, load, and manage plugins.

Plugin types (declared in plugin.json):
  app      — requires a running exe (e.g. Elite Dangerous). Started/stopped
             based on user-configured exe_path.
  service  — connects to a local service (e.g. OpenRGB SDK). Always started
             when enabled; connector reports availability.
  multi    — requires multiple processes (e.g. RTSS + Afterburner). Started
             only when ALL requirements are met.

A global check runs every 60 seconds (called from main.py).
"""

import importlib
import json
import logging
import os
import psutil

log = logging.getLogger("iris.plugins")

_PLUGIN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plugins")
_instances = {}
_manifests = {}
_cfg = {}
_serial_sender = None
_overlays = None


def _plugin_path(name):
    return os.path.join(_PLUGIN_DIR, name)


def discover_plugins():
    """Return list of (name, manifest) for all installed plugins."""
    if not os.path.isdir(_PLUGIN_DIR):
        return []
    result = []
    for entry in sorted(os.listdir(_PLUGIN_DIR)):
        mpath = os.path.join(_PLUGIN_DIR, entry, "plugin.json")
        if os.path.isfile(mpath):
            try:
                with open(mpath) as f:
                    manifest = json.load(f)
                manifest.setdefault("name", entry)
                manifest.setdefault("type", "service")
                manifest.setdefault("message_not_running", "")
                manifest.setdefault("settings", [])
                manifest.setdefault("buttons", [])
                manifest.setdefault("preset_layout", [])
                try:
                    mod = importlib.import_module(f"plugins.{entry}.connector")
                    for name_in_mod in dir(mod):
                        obj = getattr(mod, name_in_mod)
                        if isinstance(obj, type) and hasattr(obj, "controls"):
                            ctrl_list = obj.controls()
                            if ctrl_list:
                                manifest["controls"] = ctrl_list
                            if hasattr(obj, "get_settings"):
                                conn_settings = obj.get_settings()
                                if conn_settings:
                                    _merge_settings(manifest, conn_settings)
                            break
                except Exception:
                    pass
                _manifests[entry] = manifest
                result.append((entry, manifest))
            except Exception as e:
                log.warning("[pm] invalid manifest %s: %s", mpath, e)
    return result


def _merge_settings(manifest, connector_settings):
    """Merge connector-declared settings into plugin.json settings.

    Connector settings override plugin.json settings with the same title.
    If a section title from the connector matches an existing section,
    its controls replace the existing ones.  New sections are appended.
    """
    existing = manifest.get("settings", [])
    existing_titles = {s.get("title") for s in existing}
    for section in connector_settings:
        title = section.get("title")
        if title in existing_titles:
            for i, s in enumerate(existing):
                if s.get("title") == title:
                    existing[i] = section
                    break
        else:
            existing.append(section)
            existing_titles.add(title)
    manifest["settings"] = existing


def get_manifest(name):
    """Return the manifest dict for a named plugin."""
    return _manifests.get(name, {})


def refresh_settings(name):
    """Re-merge connector get_settings() into the cached manifest.

    Lets the panel pick up unit/range changes (e.g. the °F toggle)
    without an app restart. Idempotent — sections merge by title.
    """
    manifest = _manifests.get(name)
    if not manifest:
        return
    try:
        mod = importlib.import_module(f"plugins.{name}.connector")
        for obj in vars(mod).values():
            if isinstance(obj, type) and hasattr(obj, "get_settings"):
                conn_settings = obj.get_settings()
                if conn_settings:
                    _merge_settings(manifest, conn_settings)
                break
    except Exception:
        pass


def load_plugin(name, cfg, serial_sender=None, overlays=None):
    """Import and instantiate a plugin by name. Returns None on failure."""
    try:
        mod = importlib.import_module(f"plugins.{name}.plugin")
        cls = getattr(mod, "Plugin", None)
        if cls is None:
            log.warning("[pm] %s has no Plugin class", name)
            return None
        return cls(cfg, serial_sender, overlays)
    except Exception as e:
        log.warning("[pm] failed to load %s: %s", name, e)
        return None


def start_all(cfg, serial_sender=None, overlays=None):
    """Discover, load, and start all plugins."""
    global _cfg, _serial_sender, _overlays
    _cfg = cfg
    _serial_sender = serial_sender
    _overlays = overlays
    discover_plugins()
    check_plugins()


def stop_all():
    """Stop all running plugins."""
    for name, inst in list(_instances.items()):
        try:
            inst.stop()
        except Exception as e:
            log.warning("[pm] %s stop failed: %s", name, e)
    _instances.clear()


def get(name):
    """Return a running plugin instance by name, or None."""
    return _instances.get(name)


def poll_all():
    """Call poll() on all running plugins and return merged data dict."""
    data = {}
    for name, inst in list(_instances.items()):
        try:
            if hasattr(inst, "poll"):
                result = inst.poll()
                if result:
                    data[name] = result
        except Exception as e:
            log.warning("[pm] %s poll failed: %s", name, e)
    return data


def on_tap(plugin_name, control_id, value=None):
    """Dispatch a panel tile tap to the correct plugin."""
    inst = _instances.get(plugin_name)
    if inst is None:
        log.warning("[pm] tap on unknown plugin %s", plugin_name)
        return
    try:
        inst.on_tap(control_id, value)
    except Exception as e:
        log.warning("[pm] %s.on_tap(%s) failed: %s", plugin_name, control_id, e)


def invoke_action(plugin_name, action_id):
    """Invoke a declarative action on a plugin (from settings UI)."""
    inst = _instances.get(plugin_name)
    if inst is None:
        log.warning("[pm] action on unknown plugin %s", plugin_name)
        return False
    try:
        if hasattr(inst, "on_action"):
            inst.on_action(action_id)
            return True
        log.warning("[pm] %s has no on_action method", plugin_name)
        return False
    except Exception as e:
        log.warning("[pm] %s.on_action(%s) failed: %s", plugin_name, action_id, e)
        return False


# ── Plugin config ──────────────────────────────────────────────

def get_plugin_config(name):
    """Get config for a specific plugin from the main cfg."""
    plugins_cfg = _cfg.get("plugins", {})
    return plugins_cfg.get(name, {})


def set_plugin_config(name, data):
    """Save config for a specific plugin."""
    plugins_cfg = _cfg.setdefault("plugins", {})
    plugins_cfg[name] = data
    from config import save_config
    save_config(_cfg)


def is_running(name):
    """Check if a named plugin instance is currently active."""
    return name in _instances


def get_plugin_outputs(name):
    """Return current output routing for a plugin."""
    pcfg = _cfg.get("plugins", {}).get(name, {})
    return pcfg.get("outputs", {})


def set_plugin_outputs(name, outputs):
    """Save output routing for a plugin."""
    pcfg = _cfg.setdefault("plugins", {}).setdefault(name, {})
    pcfg["outputs"] = outputs
    from config import save_config
    save_config(_cfg)


# ── Process detection ──────────────────────────────────────────

def is_exe_running(exe_name):
    """Check if a process with the given exe name is running."""
    if not exe_name:
        return False
    exe_lower = exe_name.lower().strip()
    for proc in psutil.process_iter(["name"]):
        try:
            if proc.info["name"] and proc.info["name"].lower() == exe_lower:
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False


def _check_requirements(requirements):
    """Check all requirements for a multi-type plugin. Returns (all_met, details)."""
    details = []
    all_met = True
    for req in requirements:
        met = is_exe_running(req.get("exe", ""))
        details.append({
            "name": req.get("name", "?"),
            "exe": req.get("exe", ""),
            "description": req.get("description", ""),
            "met": met,
        })
        if not met:
            all_met = False
    return all_met, details


def _start_plugin(name):
    """Start a plugin by name. Returns True on success."""
    if name in _instances:
        return True
    try:
        inst = load_plugin(name, _cfg, _serial_sender, _overlays)
        if inst is not None:
            inst.start()
            _instances[name] = inst
            log.info("[pm] started %s", name)
            return True
    except Exception as e:
        log.warning("[pm] %s start failed: %s", name, e)
    return False


def _stop_plugin(name):
    """Stop a plugin by name."""
    if name not in _instances:
        return
    try:
        _instances[name].stop()
    except Exception as e:
        log.warning("[pm] %s stop failed: %s", name, e)
    del _instances[name]
    log.info("[pm] stopped %s", name)


# ── Lifecycle check ────────────────────────────────────────────

def check_plugins():
    """Check all plugins and start/stop based on type and status.

    Called on startup and every 60 seconds from main.py.
    """
    if not _cfg:
        return

    if not _manifests:
        discover_plugins()

    plugins_cfg = _cfg.get("plugins", {})

    for name, manifest in _manifests.items():
        pcfg = plugins_cfg.get(name, {})
        enabled = pcfg.get("enabled", True)
        ptype = manifest.get("type", "service")

        if not enabled:
            _stop_plugin(name)
            continue

        should_be_active = False

        if ptype == "app":
            exe = pcfg.get("exe_path", "") or manifest.get("exe_default", "")
            should_be_active = is_exe_running(exe)

        elif ptype == "service":
            should_be_active = True

        elif ptype == "multi":
            reqs = manifest.get("requirements", [])
            all_met, _ = _check_requirements(reqs)
            should_be_active = all_met

        if should_be_active:
            _start_plugin(name)
        else:
            _stop_plugin(name)


# ── Rich status for API ────────────────────────────────────────

def get_plugin_status(name):
    """Return rich status info for a plugin.

    Returns dict with: status_code, status_label, message, requirements (for multi).
    """
    manifest = _manifests.get(name, {})
    pcfg = _cfg.get("plugins", {})
    plugin_cfg = pcfg.get(name, {})
    enabled = plugin_cfg.get("enabled", True)
    ptype = manifest.get("type", "service")
    running = name in _instances

    if not enabled:
        return {
            "status_code": "disabled",
            "status_label": "Disabled",
            "message": "",
            "requirements": [],
        }

    if ptype == "app":
        exe = plugin_cfg.get("exe_path", "") or manifest.get("exe_default", "")
        if running:
            return {
                "status_code": "running",
                "status_label": "Running",
                "message": "",
                "requirements": [],
            }
        else:
            return {
                "status_code": "waiting",
                "status_label": "Waiting for app",
                "message": manifest.get("message_not_running", ""),
                "exe_path": exe,
                "requirements": [],
            }

    if ptype == "service":
        if running:
            try:
                inst = _instances[name]
                available = inst.poll().get("available", True) if hasattr(inst, "poll") else True
            except Exception:
                available = True
            if available:
                return {
                    "status_code": "connected",
                    "status_label": "Connected",
                    "message": "",
                    "requirements": [],
                }
            else:
                return {
                    "status_code": "disconnected",
                    "status_label": "Disconnected",
                    "message": manifest.get("message_not_running", ""),
                    "requirements": [],
                }
        else:
            return {
                "status_code": "inactive",
                "status_label": "Inactive",
                "message": manifest.get("message_not_running", ""),
                "requirements": [],
            }

    if ptype == "multi":
        reqs = manifest.get("requirements", [])
        all_met, details = _check_requirements(reqs)
        if running:
            return {
                "status_code": "connected",
                "status_label": "Connected",
                "message": "",
                "requirements": details,
            }
        else:
            missing = [d["name"] for d in details if not d["met"]]
            return {
                "status_code": "missing",
                "status_label": "Missing: " + ", ".join(missing),
                "message": manifest.get("message_not_running", ""),
                "requirements": details,
            }

    return {
        "status_code": "unknown",
        "status_label": "Unknown",
        "message": "",
        "requirements": [],
    }


# ── Plugin Button Controls ────────────────────────────────────

def get_plugin_buttons(name):
    """Return list of button definitions exported by the named plugin."""
    manifest = _manifests.get(name) or {}
    return manifest.get("buttons", [])


def get_all_plugin_buttons():
    """Return dict of {plugin_name: [button_defs]} for all plugins."""
    result = {}
    for name, manifest in _manifests.items():
        btns = manifest.get("buttons") or []
        if btns:
            result[name] = btns
    return result


def _parse_button_state_value(val, labels):
    """Parse plugin state value into (is_on: bool, label_text: str, raw_value: Any).

    Supports:
      - Explicit Dict: {"active": 1/0, "label": "DOWN"} or {"on": True, "value": "..."}
      - Explicit Tuple/List: ("DOWN", 1) or (1, "DOWN") or ["DOWN", 0]
      - Pure Boolean / Int: True/1 (ON) or False/0 (OFF) -> mapped to labels["on"]/labels["off"]
      - String matching: matches labels["on"] (ON) or labels["off"] (OFF) case-insensitively
      - Fallback keywords for legacy string values
    """
    labels = labels or {}
    lbl_on = str(labels.get("on", "ON"))
    lbl_off = str(labels.get("off", "OFF"))

    if val is None:
        return False, lbl_off, None

    # 1. Dict payload
    if isinstance(val, dict):
        if "active" in val:
            is_on = bool(val["active"])
        elif "on" in val:
            is_on = bool(val["on"])
        elif "is_on" in val:
            is_on = bool(val["is_on"])
        elif "state" in val and isinstance(val["state"], (bool, int, float)):
            is_on = bool(val["state"])
        else:
            is_on = False
        lbl = val.get("label") or val.get("text") or (lbl_on if is_on else lbl_off)
        return is_on, str(lbl), val

    # 2. Tuple / List payload: (label, 1/0) or (1/0, label)
    if isinstance(val, (tuple, list)) and len(val) >= 2:
        elem0, elem1 = val[0], val[1]
        if isinstance(elem1, (bool, int, float)):
            is_on = bool(elem1)
            lbl = str(elem0)
        elif isinstance(elem0, (bool, int, float)):
            is_on = bool(elem0)
            lbl = str(elem1)
        else:
            is_on = (str(elem1).strip().lower() == lbl_on.strip().lower() or
                     str(elem1).strip().lower() in ("1", "true", "on", "active"))
            lbl = str(elem0)
        return is_on, lbl, val

    # 3. Pure Boolean
    if isinstance(val, bool):
        is_on = val
        lbl = lbl_on if is_on else lbl_off
        return is_on, lbl, val

    # 4. Numeric (int / float)
    if isinstance(val, (int, float)):
        is_on = bool(val > 0)
        lbl = lbl_on if is_on else lbl_off
        return is_on, lbl, val

    # 5. String value
    if isinstance(val, str):
        v_clean = val.strip().lower()
        on_clean = lbl_on.strip().lower()
        off_clean = lbl_off.strip().lower()

        if v_clean == on_clean:
            is_on = True
            lbl = val
        elif v_clean == off_clean:
            is_on = False
            lbl = val
        elif v_clean in ("1", "true", "on", "active", "down", "deployed", "charging", "online", "yes", "docked", "landed"):
            is_on = True
            lbl = val if val else lbl_on
        elif v_clean in ("0", "false", "off", "inactive", "up", "retracted", "offline", "no"):
            is_on = False
            lbl = val if val else lbl_off
        else:
            is_on = False
            lbl = val

        return is_on, lbl, val

    return False, str(val), val


def get_plugin_button_states():
    """Collect live state {f'{plugin}:{button_id}': {'active': bool, 'value': any, 'label': str}}."""
    import time
    states = {}
    for pname, inst in _instances.items():
        manifest = _manifests.get(pname, {})
        buttons = manifest.get("buttons", [])
        if not buttons:
            continue
        p_state = {}
        p_status = {}
        try:
            if hasattr(inst, "poll"):
                polled = inst.poll()
                if isinstance(polled, dict):
                    p_state = polled.get("state") or polled
                    p_status = polled.get("status") or {}
            elif hasattr(inst, "state"):
                p_state = inst.state()
        except Exception:
            pass

        for btn in buttons:
            bid = btn.get("id")
            skey = btn.get("state_key")
            if not bid or not skey:
                continue

            val = p_status.get(skey)
            if val is None:
                val = p_state.get(skey)

            labels = btn.get("labels") or {}
            is_on, lbl, val_raw = _parse_button_state_value(val, labels)

            states[f"{pname}:{bid}"] = {
                "active": bool(is_on),
                "value": val_raw,
                "label": str(lbl),
                "timestamp": time.time(),
            }
    return states


def handle_button_action(plugin_name, button_id, slot_data=None):
    """Trigger action for a plugin button (via plugin handler or hardware keystroke)."""
    slot_data = slot_data or {}
    manifest = _manifests.get(plugin_name, {})
    btn_def = next((b for b in manifest.get("buttons", []) if b.get("id") == button_id), None)

    # 1. Check if plugin instance defines on_button
    inst = _instances.get(plugin_name)
    if inst and hasattr(inst, "on_button"):
        try:
            res = inst.on_button(button_id, slot_data)
            if res is not None:
                return {"ok": bool(res)}
        except Exception as ex:
            log.warning("[pm] plugin %s on_button failed: %s", plugin_name, ex)

    # 2. Fallback to keybind / hotkey injection
    hotkey = slot_data.get("hotkey") or (btn_def.get("default_hotkey") if btn_def else None)
    if hotkey:
        try:
            from keyboard_service import keyboard_service
            keyboard_service.send_hotkey(hotkey)
            log.info("[pm] dispatched hotkey '%s' for %s:%s", hotkey, plugin_name, button_id)
            return {"ok": True, "hotkey": hotkey}
        except Exception as ex:
            log.warning("[pm] keyboard injection failed for %s:%s: %s", plugin_name, button_id, ex)
            return {"ok": False, "error": str(ex)}

    return {"ok": True}
