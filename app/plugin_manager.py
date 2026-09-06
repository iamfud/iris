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
import importlib.util
import json
import logging
import os
import psutil
import paths

log = logging.getLogger("iris.plugins")


def builtin_plugins_dir():
    """Return the built-in plugins directory."""
    return paths.get_builtin_plugins_dir()


def user_plugins_dir():
    """Return the user plugin directory, creating it if it doesn't exist."""
    return paths.get_user_plugins_dir()


# Kept for compatibility
_BUILTIN_PLUGIN_DIR = builtin_plugins_dir()
_USER_PLUGIN_DIR = user_plugins_dir()

_instances = {}
_manifests = {}
_cfg = {}
_serial_sender = None
_overlays = None


def _plugin_path(name):
    """Return the directory for a named plugin, preferring user over built-in."""
    u_dir = user_plugins_dir()
    b_dir = builtin_plugins_dir()
    user = os.path.join(u_dir, name)
    if os.path.isdir(user):
        return user
    return os.path.join(b_dir, name)


_DISCOVERED_CACHE = None


def invalidate_plugin_discovery():
    global _DISCOVERED_CACHE
    _DISCOVERED_CACHE = None


def discover_plugins(force=False):
    """Return list of (name, manifest) for all installed plugins.

    Scans the single plugins folder (built-in + user add-ons share it).
    Location: portable -> <root>/plugins, installed -> Documents/Iris/plugins.
    """
    global _DISCOVERED_CACHE
    if not force and _DISCOVERED_CACHE is not None:
        return list(_DISCOVERED_CACHE)

    # Collect entries from both dirs; user plugins take precedence by name
    seen = {}  # name -> (plugin_dir, is_user)
    b_dir = builtin_plugins_dir()
    u_dir = user_plugins_dir()
    for base, is_user in [(b_dir, False), (u_dir, True)]:
        if not os.path.isdir(base):
            continue
        for entry in sorted(os.listdir(base)):
            mpath = os.path.join(base, entry, "plugin.json")
            if os.path.isfile(mpath):
                seen[entry] = (base, is_user)

    # Put the parent of the 'plugins' package and the app directory (for iris_plugin)
    # on sys.path so that imports resolve cleanly in both source and frozen builds.
    import sys
    root = paths.plugins_root()
    if root not in sys.path:
        sys.path.insert(0, root)
    app_dir = paths.get_app_dir()
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)

    result = []
    for entry in sorted(seen):
        base, is_user = seen[entry]
        plugin_dir = os.path.join(base, entry)
        mpath = os.path.join(plugin_dir, "plugin.json")
        try:
            with open(mpath, encoding="utf-8") as f:
                manifest = json.load(f)
            manifest.setdefault("name", entry)
            manifest.setdefault("type", "service")
            manifest.setdefault("message_not_running", "")
            manifest.setdefault("settings", [])
            manifest.setdefault("buttons", [])
            manifest.setdefault("preset_layout", [])
            manifest["user_plugin"] = is_user
            try:
                mod = importlib.import_module(f"plugins.{entry}.connector")
                for name_in_mod in dir(mod):
                    obj = getattr(mod, name_in_mod)
                    if isinstance(obj, type) and (hasattr(obj, "controls") or hasattr(obj, "get_settings")):
                        if hasattr(obj, "controls"):
                            ctrl_list = obj.controls()
                            if ctrl_list:
                                manifest["controls"] = ctrl_list
                        conn_settings = None
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
    _DISCOVERED_CACHE = list(result)
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


def is_hardware_plugin(name, manifest=None):
    """Return True if the plugin is a hardware addon/plugin.

    Plugins declare themselves as hardware plugins by specifying in plugin.json:
      "hardware_plugin": true
    or
      "type": "hardware"
    or
      "category": "hardware"
    or
      "capabilities": {"hardware": true, "lighting_provider": true, ...}

    Built-in hardware integrations (ha, openrgb, matrix_display) are also recognized.
    """
    if name in ("ha", "openrgb", "matrix_display"):
        return True
    if manifest is None:
        manifest = get_manifest(name) or {}
    if manifest.get("hardware_plugin") or manifest.get("hardware") or manifest.get("category") == "hardware":
        return True
    if manifest.get("type") == "hardware":
        return True
    caps = manifest.get("capabilities") or {}
    if caps.get("hardware") or caps.get("lighting_provider"):
        return True
    return False


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


class SerialSenderOutputProxy:
    """Wraps serial_sender to enforce the 'display' output routing toggle."""
    def __init__(self, target, plugin_name):
        self._target = target
        self._plugin_name = plugin_name

    def _is_enabled(self):
        outputs = get_plugin_outputs(self._plugin_name)
        if isinstance(outputs, dict) and "display" in outputs:
            return bool(outputs["display"])
        manifest = get_manifest(self._plugin_name) or {}
        for o in manifest.get("outputs") or []:
            if o.get("id") == "display":
                return bool(o.get("enabled", True))
        return True

    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr

        # Clears, releases, and button warning states ALWAYS pass through
        if any(w in name for w in ("release", "clear", "stop", "warning")):
            return attr

        def wrapper(*args, **kwargs):
            if not self._is_enabled():
                return None
            return attr(*args, **kwargs)
        return wrapper


class OverlaysOutputProxy:
    """Wraps overlays to enforce the 'overlay' output routing toggle."""
    def __init__(self, target, plugin_name):
        self._target = target
        self._plugin_name = plugin_name

    def _is_enabled(self):
        outputs = get_plugin_outputs(self._plugin_name)
        if isinstance(outputs, dict) and "overlay" in outputs:
            return bool(outputs["overlay"])
        manifest = get_manifest(self._plugin_name) or {}
        for o in manifest.get("outputs") or []:
            if o.get("id") == "overlay":
                return bool(o.get("enabled", True))
        return True

    def __getattr__(self, name):
        attr = getattr(self._target, name)
        if not callable(attr):
            return attr

        if any(w in name for w in ("hide", "clear", "dismiss", "stop")):
            return attr

        def wrapper(*args, **kwargs):
            if not self._is_enabled():
                return None
            return attr(*args, **kwargs)
        return wrapper


def load_plugin(name, cfg, serial_sender=None, overlays=None):
    """Import and instantiate a plugin by name. Returns None on failure."""
    try:
        mod = None
        try:
            mod = importlib.import_module(f"plugins.{name}.plugin")
        except ModuleNotFoundError:
            p_dir = _plugin_path(name)
            p_file = os.path.join(p_dir, "plugin.py")
            if os.path.isfile(p_file):
                spec = importlib.util.spec_from_file_location(f"plugins.{name}.plugin", p_file)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
        if mod is None:
            log.warning("[pm] could not find plugin module for %s", name)
            return None
        cls = getattr(mod, "Plugin", None)
        if cls is None:
            log.warning("[pm] %s has no Plugin class", name)
            return None
        wrapped_serial = SerialSenderOutputProxy(serial_sender, name) if serial_sender is not None else None
        wrapped_overlays = OverlaysOutputProxy(overlays, name) if overlays is not None else None
        return cls(cfg, wrapped_serial, wrapped_overlays)
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
        return False
    try:
        inst.on_tap(control_id, value)
        return True
    except Exception as e:
        log.warning("[pm] %s.on_tap(%s) failed: %s", plugin_name, control_id, e)
        return False


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

    # If display was turned off, clear any active progress/display claims immediately
    if outputs.get("display") is False and _serial_sender is not None:
        try:
            if hasattr(_serial_sender, "release_progress_prefix"):
                _serial_sender.release_progress_prefix(f"{name}.")
                _serial_sender.release_progress_prefix("ed.")
            if hasattr(_serial_sender, "clear_display_prefix"):
                _serial_sender.clear_display_prefix(f"{name}.")
                _serial_sender.clear_display_prefix("ed.")
            if hasattr(_serial_sender, "clear_display"):
                _serial_sender.clear_display()
        except Exception as e:
            log.debug("[pm] error clearing serial display on output disable: %s", e)


# ── Process detection ──────────────────────────────────────────

def is_exe_running(exe_name):
    """Check if a process with the given exe name is running."""
    if not exe_name:
        return False
    try:
        from win_platform import is_process_running
        return is_process_running(exe_name, ttl=1.0)
    except Exception:
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
            "url": req.get("url", ""),
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
    try:
        import warning_state
        warning_state.clear_plugin_warnings(name)
    except Exception:
        pass
    sync_plugin_themes()


# ── Dynamic Plugin Theme Engine ────────────────────────────────
_saved_base_theme = None
_active_themed_plugin = None


def is_exe_foreground(exe_name: str) -> bool:
    """Check if the given executable name is currently the active foreground window."""
    if not exe_name:
        return False
    try:
        import ctypes
        import psutil
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return False
        pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return False
        proc_name = psutil.Process(pid.value).name().lower().strip()
        target_name = os.path.basename(exe_name).lower().strip()
        return proc_name == target_name or (target_name and (target_name in proc_name or proc_name in target_name))
    except Exception:
        return False


def _is_plugin_focused(manifest, pcfg):
    """Check if the plugin's target executable is the active foreground window."""
    exe_target = pcfg.get("exe_path") or manifest.get("exe_default") or ""
    return is_exe_foreground(exe_target)


def sync_plugin_themes():
    """Latch-on-load theme engine: apply a profile theme when its game starts running.

    Rules:
    - Theme is latched when a profile's exe starts running (regardless of window focus).
    - Theme is NOT removed on alt-tab to desktop or unthemed apps.
    - If multiple running profiles have themes, the one whose window is currently focused
      wins. If the foreground window belongs to no themed profile (e.g. desktop, browser),
      the last active themed profile's theme stays latched.
    - Theme is restored to the user's saved base only when NO themed profile is running.
    - Per-profile flags respected: `theme_override` (CC), `lighting_theme_enabled` (OpenRGB).
    """
    global _saved_base_theme, _active_themed_plugin
    if not _cfg or not isinstance(_cfg, dict):
        return

    # ── Collect all profiles that are both running and have a theme defined ──
    try:
        from panel_actions import _running_profile_exes
        profiles = _cfg.get("panel_profiles") or []
        running_exes = _running_profile_exes(profiles)
    except Exception:
        profiles = []
        running_exes = set()

    def _profile_theme(p):
        """Return the effective theme dict for a profile (profile.theme or linked plugin manifest theme)."""
        t = p.get("theme")
        if t and isinstance(t, dict) and (t.get("accent") or t.get("neon")):
            return t
        # Fall back to linked plugin manifest theme
        pexe = str(p.get("exe") or "").lower().replace(".exe", "").strip()
        for name, manifest in _manifests.items():
            mtheme = manifest.get("theme")
            if not mtheme or not isinstance(mtheme, dict):
                continue
            mexe = str(manifest.get("exe_default") or "").lower().replace(".exe", "").strip()
            if pexe and mexe and (pexe == mexe or pexe in mexe or mexe in pexe):
                return mtheme
        return None

    running_themed = []
    covered_exes = set()
    for p in profiles:
        if not isinstance(p, dict) or not p.get("enabled", True):
            continue
        if p.get("id") == "__default__":
            continue
        pexe = str(p.get("exe") or "").lower().replace(".exe", "").strip()
        if not pexe or pexe not in running_exes:
            continue
        # A profile qualifies if it has a theme, OR if either feature toggle is on.
        # Don't use the theme dict as a gate — the CC/lighting flags are independent.
        th = _profile_theme(p)
        wants_cc = p.get("theme_override", True)
        wants_lighting = p.get("lighting_theme_enabled", True)
        if th or wants_cc or wants_lighting:
            running_themed.append((p, th or {}))
            covered_exes.add(pexe)

    # ── Also check legacy plugin-level themes (plugins without a profile) ──
    # (keeps backward compat for plugin manifests that declare theme directly)
    legacy_candidate = None
    for name, manifest in _manifests.items():
        theme_def = manifest.get("theme")
        if not theme_def or not isinstance(theme_def, dict):
            continue
        pcfg = _cfg.get("plugins", {}).get(name, {})
        if not pcfg.get("enabled", True):
            continue
        if pcfg.get("auto_theme") is False:
            continue
        exe_target = pcfg.get("exe_path") or manifest.get("exe_default") or ""
        exe_key = str(exe_target).lower().replace(".exe", "").strip()
        # Only pick up legacy if NOT already covered by a real profile
        if exe_key not in covered_exes and exe_key in running_exes:
            legacy_candidate = (name, theme_def)
            break

    if not running_themed and legacy_candidate:
        # Wrap legacy plugin as a synthetic profile for uniform handling
        name, theme_def = legacy_candidate
        synthetic = {
            "id": f"__plugin_{name}__",
            "exe": name,
            "theme_override": True,
            "lighting_theme_enabled": True,
        }
        running_themed.append((synthetic, theme_def))

    if not running_themed:
        # ── No themed profiles running → restore base user theme ──
        if _active_themed_plugin is not None and _saved_base_theme is not None:
            log.info("[pm] no themed profile running — restoring base theme: %s", _saved_base_theme)
            _cfg["theme"] = dict(_saved_base_theme)
            _broadcast_theme(_saved_base_theme)
            _saved_base_theme = None
            _active_themed_plugin = None
        return

    # ── One or more themed profiles running ──
    # Pick which one to show: if any running themed profile is currently focused, use it.
    # Otherwise keep the currently active one (sticky latch — do NOT unload).
    selected_profile = None
    selected_theme = None

    if len(running_themed) == 1:
        selected_profile, selected_theme = running_themed[0]
    else:
        # Multiple themed profiles: try to match foreground window
        try:
            from panel_actions import foreground_exe
            fg = foreground_exe()
            fg_key = str(fg or "").lower().replace(".exe", "").strip()
        except Exception:
            fg_key = ""

        for p, th in running_themed:
            pexe = str(p.get("exe") or "").lower().replace(".exe", "").strip()
            if fg_key and (pexe == fg_key or fg_key in pexe or pexe in fg_key):
                selected_profile, selected_theme = p, th
                break

        if selected_profile is None:
            # Foreground is not a themed profile (e.g. desktop, browser) → keep current latch
            if _active_themed_plugin is not None:
                # Already latched — do nothing (sticky)
                return
            # First time: default to the first running themed profile
            selected_profile, selected_theme = running_themed[0]

    # ── Apply theme if it changed ──
    candidate_id = selected_profile.get("id") or selected_profile.get("exe") or ""
    if _active_themed_plugin == candidate_id:
        return  # Already active — nothing to do

    # Snapshot user's base theme before first takeover
    if _saved_base_theme is None:
        cur_th = _cfg.get("theme") or {}
        _saved_base_theme = {
            "mode": cur_th.get("mode", "iris"),
            "accent": cur_th.get("accent", "#B23AF6"),
            "neon": cur_th.get("neon", "#48B2E9"),
        }

    _active_themed_plugin = candidate_id

    # Control-Centre theme — re-resolve at apply time so manifest fallback works
    # even when selected_theme was stored as {} (no custom colours on the profile).
    if selected_profile.get("theme_override", True):
        resolved_theme = selected_theme if (selected_theme.get("accent") or selected_theme.get("neon")) \
            else _profile_theme(selected_profile)
        if resolved_theme:
            theme_payload = {
                "mode": resolved_theme.get("mode", "custom"),
                "accent": resolved_theme.get("accent", "#ff5500"),
                "neon": resolved_theme.get("neon", "#ffaa00"),
            }
            _cfg["theme"] = theme_payload
            log.info("[pm] latched game theme for '%s': %s", candidate_id, theme_payload)
            _broadcast_theme(theme_payload)

    # Hardware Lighting theme
    if selected_profile.get("lighting_theme_enabled", True):
        try:
            from lighting_service import get_lighting_service
            get_lighting_service().evaluate_state(force=True)
        except Exception as ex:
            log.debug("[pm] lighting evaluate_state failed: %s", ex)


def _broadcast_theme(theme_dict):
    try:
        import ws_bridge
        ws_bridge.broadcast({"type": "theme", "theme": theme_dict})
    except Exception:
        pass


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

    sync_plugin_themes()


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
                if hasattr(inst, "is_connected"):
                    available = bool(inst.is_connected())
                elif hasattr(inst, "poll"):
                    available = bool(inst.poll().get("available", False))
                else:
                    available = True
            except Exception:
                available = False
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
    has_custom_labels = bool(labels.get("on") or labels.get("off"))
    lbl_on = str(labels.get("on", "ON"))
    lbl_off = str(labels.get("off", "OFF"))

    if val is None:
        return False, lbl_off if has_custom_labels else "0", None

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
        if has_custom_labels:
            lbl = lbl_on if is_on else lbl_off
        else:
            lbl = f"{int(val)} JUMPS" if (isinstance(val, int) or val.is_integer()) else f"{val:.1f}"
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

            # Support dynamic max bounds via max_key or static max
            b_max = btn.get("max")
            max_key = btn.get("max_key")
            if max_key:
                dyn_max = p_status.get(max_key)
                if dyn_max is None:
                    dyn_max = p_state.get(max_key)
                if dyn_max is not None:
                    try:
                        b_max = float(dyn_max)
                    except (ValueError, TypeError):
                        pass

            b_min = btn.get("min", 0)

            b_entry = {
                "active": bool(is_on),
                "value": val_raw,
                "label": str(lbl),
                "timestamp": time.time(),
            }
            if "display_mode" in btn:
                b_entry["display_mode"] = btn["display_mode"]
            if "unit" in btn:
                b_entry["unit"] = btn["unit"]
            if b_max is not None:
                b_entry["max"] = b_max
            if b_min is not None:
                b_entry["min"] = b_min

            states[f"{pname}:{bid}"] = b_entry
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
