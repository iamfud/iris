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
                try:
                    mod = importlib.import_module(f"plugins.{entry}.connector")
                    for name_in_mod in dir(mod):
                        obj = getattr(mod, name_in_mod)
                        if isinstance(obj, type) and hasattr(obj, "controls"):
                            ctrl_list = obj.controls()
                            if ctrl_list:
                                manifest["controls"] = ctrl_list
                            break
                except Exception:
                    pass
                _manifests[entry] = manifest
                result.append((entry, manifest))
            except Exception as e:
                log.warning("[pm] invalid manifest %s: %s", mpath, e)
    return result


def get_manifest(name):
    """Return the manifest dict for a named plugin."""
    return _manifests.get(name, {})


def load_plugin(name, cfg, serial_sender=None):
    """Import and instantiate a plugin by name. Returns None on failure."""
    try:
        mod = importlib.import_module(f"plugins.{name}.plugin")
        cls = getattr(mod, "Plugin", None)
        if cls is None:
            log.warning("[pm] %s has no Plugin class", name)
            return None
        return cls(cfg, serial_sender)
    except Exception as e:
        log.warning("[pm] failed to load %s: %s", name, e)
        return None


def start_all(cfg, serial_sender=None):
    """Discover, load, and start all plugins."""
    global _cfg, _serial_sender
    _cfg = cfg
    _serial_sender = serial_sender
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
        inst = load_plugin(name, _cfg, _serial_sender)
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
