"""Elite Dangerous Bindings Scanner & Auto-Sync Engine.

Discovers the player's active .binds XML file from Frontier Options,
creates timestamped backups in Iris plugin data, parses keyboard
bindings, and automatically synchronizes button hotkeys across all
active Iris button profiles.
"""

import glob
import hashlib
import logging
import os
import shutil
import time
import xml.etree.ElementTree as ET

log = logging.getLogger("iris.ed.binds")

# Frontier Key to Iris Hotkey Translation Table
FRONTIER_KEY_MAP = {
    # Modifiers
    "Key_LeftControl": "ctrl",
    "Key_RightControl": "ctrl",
    "Key_LeftShift": "shift",
    "Key_RightShift": "shift",
    "Key_LeftAlt": "alt",
    "Key_RightAlt": "alt",
    "Key_LeftWindows": "win",
    "Key_RightWindows": "win",
    # Special keys
    "Key_Space": "space",
    "Key_Enter": "enter",
    "Key_Return": "enter",
    "Key_Tab": "tab",
    "Key_Escape": "esc",
    "Key_Backspace": "backspace",
    "Key_Insert": "insert",
    "Key_Delete": "delete",
    "Key_Home": "home",
    "Key_End": "end",
    "Key_PageUp": "pageup",
    "Key_PageDown": "pagedown",
    "Key_UpArrow": "up",
    "Key_DownArrow": "down",
    "Key_LeftArrow": "left",
    "Key_RightArrow": "right",
    # Punctuation / symbols
    "Key_SemiColon": ";",
    "Key_Apostrophe": "'",
    "Key_LeftBracket": "[",
    "Key_RightBracket": "]",
    "Key_BackSlash": "\\",
    "Key_Comma": ",",
    "Key_Period": ".",
    "Key_Slash": "/",
    "Key_Minus": "-",
    "Key_Equals": "=",
    "Key_Grave": "`",
    "Key_Capital": "capslock",
    "Key_ScrollLock": "scrolllock",
    "Key_NumLock": "numlock",
    "Key_PrintScreen": "printscreen",
    "Key_Pause": "pause",
}

# Add function keys F1-F12
for _i in range(1, 13):
    FRONTIER_KEY_MAP[f"Key_F{_i}"] = f"f{_i}"

# Add numpad keys
for _i in range(10):
    FRONTIER_KEY_MAP[f"Key_Numpad_{_i}"] = f"num{_i}"
FRONTIER_KEY_MAP["Key_Numpad_Add"] = "num+"
FRONTIER_KEY_MAP["Key_Numpad_Subtract"] = "num-"
FRONTIER_KEY_MAP["Key_Numpad_Multiply"] = "num*"
FRONTIER_KEY_MAP["Key_Numpad_Divide"] = "num/"
FRONTIER_KEY_MAP["Key_Numpad_Decimal"] = "num."
FRONTIER_KEY_MAP["Key_Numpad_Enter"] = "enter"

# XML Action Tag to Iris Button ID Mapping
XML_ACTION_TO_BUTTON_ID = {
    # Flight & Ship Controls
    "LandingGearToggle": "landing_gear",
    "DeployHardpointToggle": "hardpoints",
    "ToggleCargoScoop": "cargo_scoop",
    "HyperSuperCombination": "fsd",
    "Hyperspace": "hyperspace",
    "Supercruise": "supercruise",
    "HeadlightsToggle": "lights",
    "ShipSpotLightToggle": "lights",
    "NightVisionToggle": "night_vision",
    "ToggleFlightAssist": "flight_assist",
    "FlightAssist": "flight_assist",
    # Countermeasures & Utilities
    "DeployHeatSink": "heatsink",
    "FireChaffLauncher": "chaff",
    "UseShieldCell": "shield_cell",
    "ChargeECM": "ecm",
    # Navigation & Targeting
    "GalaxyMapOpen": "galaxy_map",
    "SystemMapOpen": "system_map",
    "SelectHighestThreat": "highest_threat",
    "CycleNextTarget": "next_target",
    "CyclePreviousTarget": "prev_target",
    "CycleNextHostileTarget": "next_hostile",
    "CyclePreviousHostileTarget": "prev_hostile",
    "TargetWingman0": "target_wingman_1",
    "TargetWingman1": "target_wingman_2",
    "TargetWingman2": "target_wingman_3",
    "SelectTargetsTarget": "target_wingman_target",
    # UI & Cockpit Modes
    "OrbitLinesToggle": "orbit_lines",
    "PlayerHUDModeToggle": "hud_mode",
    "MicrophoneMute": "mic_mute",
    "HMDReset": "hmd_reset",
    "PhotoCameraToggle": "camera_toggle",
    "UIFocus": "ui_focus",
    "FocusLeftPanel": "panel_nav",
    "FocusCommsPanel": "panel_comms",
    "FocusRadarPanel": "panel_role",
    "FocusRightPanel": "panel_sys",
}


def get_bindings_dir():
    """Return the default Windows path to Frontier Elite Dangerous Bindings folder."""
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return None
    p = os.path.join(local_app_data, "Frontier Developments", "Elite Dangerous", "Options", "Bindings")
    return p if os.path.isdir(p) else None


def get_active_binds_file():
    """Find and return (binds_filepath, preset_name) for the player's active bindings."""
    binds_dir = get_bindings_dir()
    if not binds_dir:
        return None, None

    active_preset = None

    # Check StartPreset files (StartPreset.4.start, StartPreset.start, etc.)
    start_files = sorted(
        glob.glob(os.path.join(binds_dir, "StartPreset*.start")),
        key=os.path.getmtime,
        reverse=True,
    )
    for sf in start_files:
        try:
            with open(sf, "r", encoding="utf-8", errors="ignore") as f:
                lines = [l.strip() for l in f if l.strip()]
                if lines:
                    for line in lines:
                        if line and line != "KeyboardMouseOnly":
                            active_preset = line
                            break
                    if not active_preset:
                        active_preset = lines[0]
                    if active_preset:
                        break
        except Exception as e:
            log.debug("[ed.binds] error reading start file %s: %s", sf, e)

    # If active preset found, look for matching .binds file
    if active_preset:
        matches = glob.glob(os.path.join(binds_dir, f"{active_preset}*.binds"))
        if matches:
            matches.sort(key=os.path.getmtime, reverse=True)
            return matches[0], active_preset

    # Fall back to the most recently modified .binds file in the directory
    all_binds = glob.glob(os.path.join(binds_dir, "*.binds"))
    if all_binds:
        all_binds.sort(key=os.path.getmtime, reverse=True)
        latest = all_binds[0]
        preset = os.path.splitext(os.path.basename(latest))[0]
        preset_clean = preset.split(".")[0]
        return latest, preset_clean

    return None, None


def get_backup_dir():
    """Return the directory path for storing Iris binds backups."""
    app_data = os.environ.get("APPDATA", "")
    if app_data:
        target = os.path.join(app_data, "Iris", "plugin_data", "elite_dangerous", "binds_backups")
    else:
        target = os.path.join(os.path.dirname(os.path.abspath(__file__)), "backups")
    os.makedirs(target, exist_ok=True)
    return target


def backup_binds_file(binds_path, preset_name=None):
    """Save a timestamped backup of the binds file if modified. Prunes old backups."""
    if not binds_path or not os.path.isfile(binds_path):
        return None

    try:
        backup_dir = get_backup_dir()
        with open(binds_path, "rb") as f:
            content = f.read()
        cur_hash = hashlib.sha256(content).hexdigest()

        # Check existing backups to avoid duplicates
        existing = glob.glob(os.path.join(backup_dir, "*.binds"))
        for eb in existing:
            try:
                with open(eb, "rb") as f:
                    if hashlib.sha256(f.read()).hexdigest() == cur_hash:
                        return eb  # Already backed up
            except Exception:
                continue

        p_name = preset_name or os.path.splitext(os.path.basename(binds_path))[0]
        safe_name = "".join(c for c in p_name if c.isalnum() or c in (" ", "_", "-")).strip().replace(" ", "_")
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        dest_filename = f"{safe_name}_{timestamp}.binds"
        dest_path = os.path.join(backup_dir, dest_filename)

        with open(dest_path, "wb") as f:
            f.write(content)
        log.info("[ed.binds] created binds backup: %s", dest_path)

        # Prune old backups keeping 30 most recent
        all_backups = sorted(glob.glob(os.path.join(backup_dir, "*.binds")), key=os.path.getmtime, reverse=True)
        if len(all_backups) > 30:
            for old_f in all_backups[30:]:
                try:
                    os.remove(old_f)
                except Exception:
                    pass

        return dest_path
    except Exception as e:
        log.warning("[ed.binds] failed to backup binds: %s", e)
        return None


MODIFIER_ORDER = {"ctrl": 0, "alt": 1, "shift": 2, "win": 3}


def _parse_key_element(elem):
    """Translate a Frontier XML key element into an Iris hotkey string (e.g. 'ctrl+l')."""
    if elem is None:
        return None

    # Check Primary first, then Secondary
    sub_elements = elem.findall("Primary") + elem.findall("Secondary")
    for sub in sub_elements:
        dev = sub.get("Device", "")
        key = sub.get("Key", "")
        if dev == "Keyboard" and key:
            mods = []
            for m in sub.findall("Modifier"):
                if m.get("Device") == "Keyboard" and m.get("Key"):
                    m_key = m.get("Key")
                    mod_name = FRONTIER_KEY_MAP.get(m_key, m_key.replace("Key_", "").lower())
                    if mod_name not in mods:
                        mods.append(mod_name)
            mods.sort(key=lambda m: MODIFIER_ORDER.get(m, 99))
            k_name = FRONTIER_KEY_MAP.get(key, key.replace("Key_", "").lower())
            return "+".join(mods + [k_name])
    return None


def list_available_binds_files():
    """Return list of filenames for all .binds files in Frontier Bindings directory."""
    binds_dir = get_bindings_dir()
    if not binds_dir:
        return []
    files = glob.glob(os.path.join(binds_dir, "*.binds"))
    files.sort(key=os.path.getmtime, reverse=True)
    return [os.path.basename(f) for f in files]


def list_available_backups():
    """Return list of backup filenames stored in Iris plugin data."""
    backup_dir = get_backup_dir()
    files = glob.glob(os.path.join(backup_dir, "*.binds"))
    files.sort(key=os.path.getmtime, reverse=True)
    return [os.path.basename(f) for f in files]


def restore_backup(backup_filename, cfg=None):
    """Restore a backup .binds file into Frontier Bindings and update StartPreset."""
    backup_dir = get_backup_dir()
    src = os.path.join(backup_dir, backup_filename)
    if not os.path.isfile(src):
        return False, f"Backup file not found: {backup_filename}"

    binds_dir = get_bindings_dir()
    if not binds_dir:
        return False, "Elite Dangerous Bindings directory not found"

    try:
        # Determine destination filename and preset name
        base = os.path.basename(backup_filename)
        # Name format: <PresetName>_<Timestamp>.binds
        if "_" in base:
            parts = base.rsplit("_", 1)
            preset_name = parts[0].replace("_", " ")
        else:
            preset_name = os.path.splitext(base)[0]

        dest_filename = f"{preset_name}.4.2.binds"
        dest_path = os.path.join(binds_dir, dest_filename)

        shutil.copy2(src, dest_path)
        log.info("[ed.binds] restored backup %s to %s", src, dest_path)

        # Update StartPreset files
        start_files = glob.glob(os.path.join(binds_dir, "StartPreset*.start"))
        if not start_files:
            start_files = [os.path.join(binds_dir, "StartPreset.4.start")]
        for sf in start_files:
            try:
                with open(sf, "w", encoding="utf-8") as f:
                    f.write(f"KeyboardMouseOnly\n{preset_name}\nKeyboardMouseOnly\nKeyboardMouseOnly\n")
            except Exception as ex:
                log.debug("[ed.binds] start file write error: %s", ex)

        # Parse and sync keys to Iris config
        if cfg is not None:
            keys = parse_binds_xml(dest_path)
            if keys:
                sync_binds_to_config(cfg, keys)
                from config import save_config
                save_config(cfg)

        return True, f"Restored {preset_name} successfully"
    except Exception as e:
        log.warning("[ed.binds] restore failed: %s", e)
        return False, str(e)


def parse_binds_xml(binds_path):
    """Parse an Elite Dangerous .binds XML file into a dict of { button_id: hotkey_string }."""
    if not binds_path or not os.path.isfile(binds_path):
        return {}

    key_map = {}
    try:
        tree = ET.parse(binds_path)
        root = tree.getroot()

        for xml_tag, button_id in XML_ACTION_TO_BUTTON_ID.items():
            elem = root.find(xml_tag)
            if elem is not None:
                hotkey = _parse_key_element(elem)
                if hotkey:
                    key_map[button_id] = hotkey
    except Exception as e:
        log.warning("[ed.binds] XML parse error for %s: %s", binds_path, e)

    return key_map


def sync_binds_to_config(cfg, key_map):
    """Update hotkey values across panel_board and panel_profiles in cfg. Returns count of modified slots."""
    if not isinstance(cfg, dict) or not key_map:
        return 0

    updated_count = 0

    # 1. Update default panel_board
    board = cfg.get("panel_board") or []
    if isinstance(board, list):
        for slot in board:
            if not isinstance(slot, dict):
                continue
            if slot.get("plugin") == "elite_dangerous":
                bid = slot.get("button_id")
                if bid and bid in key_map:
                    new_key = key_map[bid]
                    if slot.get("hotkey") != new_key:
                        slot["hotkey"] = new_key
                        updated_count += 1

    # 2. Update all panel_profiles
    profiles = cfg.get("panel_profiles") or []
    if isinstance(profiles, list):
        for prof in profiles:
            if not isinstance(prof, dict):
                continue
            p_board = prof.get("board") or []
            if isinstance(p_board, list):
                for slot in p_board:
                    if not isinstance(slot, dict):
                        continue
                    if slot.get("plugin") == "elite_dangerous":
                        bid = slot.get("button_id")
                        if bid and bid in key_map:
                            new_key = key_map[bid]
                            if slot.get("hotkey") != new_key:
                                slot["hotkey"] = new_key
                                updated_count += 1

    return updated_count


class BindsWatcher:
    """Monitors the player's active .binds file and auto-syncs hotkeys on change."""

    def __init__(self):
        self._last_file = None
        self._last_mtime = 0.0
        self._current_key_map = {}
        self._last_preset_name = None

    @property
    def current_key_map(self):
        return dict(self._current_key_map)

    def get_key(self, button_id, fallback=""):
        return self._current_key_map.get(button_id, fallback)

    def check_for_updates(self, cfg=None):
        """Check if active binds file was modified. Backs up, parses, and auto-syncs cfg."""
        try:
            active_file, preset_name = get_active_binds_file()
            if not active_file or not os.path.isfile(active_file):
                return False

            mtime = os.path.getmtime(active_file)
            if active_file == self._last_file and mtime == self._last_mtime and self._current_key_map:
                return False  # No change

            log.info("[ed.binds] active binds detected: %s (preset: %s)", active_file, preset_name)

            # 1. Create backup
            backup_binds_file(active_file, preset_name)

            # 2. Parse key mapping
            parsed_keys = parse_binds_xml(active_file)
            self._current_key_map = parsed_keys
            self._last_file = active_file
            self._last_mtime = mtime
            self._last_preset_name = preset_name

            # 3. Synchronize to config if provided
            if cfg is not None and parsed_keys:
                updated = sync_binds_to_config(cfg, parsed_keys)
                if updated > 0:
                    try:
                        from config import save_config
                        save_config(cfg)
                        log.info("[ed.binds] auto-synced %d button hotkeys to match in-game bindings", updated)
                    except Exception as e:
                        log.warning("[ed.binds] failed to save synced config: %s", e)

            return True
        except Exception as e:
            log.warning("[ed.binds] check_for_updates error: %s", e)
            return False
