"""Iris — Constants and design tokens."""

APP_VERSION = "3.0"
APP_NAME = "IRIS"

DEFAULT_CONFIG = {
    "serial_port": "auto",
    "brightness": 3,
    "pc_disp": 7,
    "feature_time": True,
    "feature_date": False,
    "feature_minute_bar": True,
    "feature_eyes": True,
    "feature_notifications": True,
    "feature_large_clock": False,
    "feature_day_clock": True,
    "night_mode_enabled": False,
    "temp_alert": True,
    "pc_stats_enabled": True,
    "cpu_temp_lim": 90,
    "gpu_temp_lim": 90,
    "ha_url": "",
    "ha_token": "",
    "ha_shortcuts": [],
    "openrgb_enabled": False,
    "openrgb_profiles": [],
    "steam_enabled": True,
    "media_enabled": True,
    "mirror_enabled": True,
    "media_player_path": "",
    "alarms": [],
    "ha_board": [],
    "pc_stats_manual": False,
}

# Device-side defaults (pushed to ESP8266 on connect / factory reset)
DEVICE_DEFAULTS = {
    "feature_time": "1",
    "feature_date": "0",
    "feature_minute_bar": "1",
    "feature_eyes": "1",
    "feature_notifications": "1",
    "feature_large_clock": "0",
    "feature_day_clock": "1",
    "night_mode_enabled": "0",
    "display_on": "1",
    "brightness": "3",
    "alarm_enabled": "0",
    "alarm_hour": "7",
    "alarm_minute": "0",
    "temp_alert": "0",
    "cpu_temp_lim": "90",
    "gpu_temp_lim": "90",
}

BG = "#202020"
BG_CARD = "#2b2b2b"
NEON = "#48B2E9"
NEON_DIM = "#555555"
BUTTON_HOVER = "#3c3c3c"
BORDER = "#2a2a2a"
FG = "#e0e0e0"
FG_DIM = "#666666"
FONT_UI = ("Segoe UI", 10)
FONT_SM = ("Segoe UI", 9)
NEON_GRN = "#00ff88"
NEON_RED = "#ff3355"
GAUGE_WARN = "#ffd166"
HA_PALETTE = [
    "#FF0000", "#FF3300", "#FF6600", "#FF8800", "#FFAA00", "#FFCC00",
    "#FFFF00", "#CCFF00", "#88FF00", "#00CC00", "#00BB44", "#00FF88",
    "#00FFCC", "#00CCFF", "#00AAFF", "#0066FF", "#0033CC", "#0000FF",
    "#6600FF", "#9900CC", "#FF00FF", "#FF0099", "#FFFFFF", "#888888",
    "#FF4444", "#FF7744", "#FF9944", "#FFBB44", "#FFDD44", "#FFEE44",
    "#DDFF44", "#AAFF44", "#44FF44", "#44FF88", "#44FFBB", "#44DDCC",
    "#44BBFF", "#4488FF", "#4455FF", "#6644FF",
]

DANGER = "#aa1a00"
DANGER_HOVER = "#cc2200"
BUTTON = "#373737"
RADIUS_CARD = 6

VK_NAMES = {
    8: "Backspace", 9: "Tab", 13: "Enter", 16: "Shift", 17: "Ctrl",
    18: "Alt", 19: "Pause", 20: "Caps", 27: "Esc", 32: "Space",
    33: "PageUp", 34: "PageDown", 35: "End", 36: "Home",
    37: "Left", 38: "Up", 39: "Right", 40: "Down",
    44: "Print", 45: "Insert", 46: "Delete",
    91: "Win", 92: "Win",
    112: "F1", 113: "F2", 114: "F3", 115: "F4", 116: "F5",
    117: "F6", 118: "F7", 119: "F8", 120: "F9", 121: "F10",
    122: "F11", 123: "F12", 124: "F13", 125: "F14", 126: "F15",
    127: "F16", 128: "F17", 129: "F18", 130: "F19", 131: "F20",
    132: "F21", 133: "F22", 134: "F23", 135: "F24",
    144: "NumLock", 145: "ScrollLock",
    186: ";", 187: "=", 188: ",", 189: "-", 190: ".", 191: "/",
    192: "`", 219: "[", 220: "\\", 221: "]", 222: "'",
}


def format_keys(keys):
    parts = []
    for vk in keys:
        name = VK_NAMES.get(vk)
        if name:
            parts.append(name)
        elif 48 <= vk <= 57:
            parts.append(chr(vk))
        elif 65 <= vk <= 90:
            parts.append(chr(vk))
        elif 96 <= vk <= 105:
            parts.append(f"Num{chr(vk - 48)}")
        else:
            parts.append(f"VK_{vk}")
    return "+".join(parts)
