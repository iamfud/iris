"""MDI icon renderer — downloads HA's icon font once, renders glyphs with PIL."""

import json
import threading
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont, ImageTk
    _PIL_OK = True
except ImportError:
    _PIL_OK = False

_APP_DIR   = Path(__file__).parent
FONT_PATH  = _APP_DIR / "mdi-webfont.ttf"
_META_PATH = _APP_DIR / "mdi-meta.json"

_FONT_URL = ("https://raw.githubusercontent.com/Templarian/"
             "MaterialDesign-Webfont/master/fonts/materialdesignicons-webfont.ttf")
_META_URL = ("https://raw.githubusercontent.com/Templarian/"
             "MaterialDesign/master/meta.json")

_codepoints: dict = {}
_font_cache: dict = {}
ready       = threading.Event()
error: str  = ""

# ── Built-in fallback codepoints (stable across MDI 5–7) ─────────────────────
_BUILTIN = {
    "account":            0xF0004,
    "alarm":              0xF0020,
    "alarm-light":        0xF0578,
    "bell":               0xF004A,
    "bell-off":           0xF1063,
    "brightness-5":       0xF0070,
    "brightness-7":       0xF0072,
    "car":                0xF00B9,
    "cog":                0xF0493,
    "cog-outline":        0xF1087,
    "coffee":             0xF00ED,
    "door":               0xF081A,
    "fan":                0xF0210,
    "flash":              0xF0224,
    "floor-lamp":         0xF08DD,
    "home":               0xF02DC,
    "home-outline":       0xF06A1,
    "lamp":               0xF06B5,
    "lightbulb":          0xF0335,
    "lightbulb-off":      0xF06D2,
    "lightbulb-on":       0xF06D4,
    "lightbulb-outline":  0xF06D6,
    "lock":               0xF033E,
    "lock-open":          0xF033F,
    "movie":              0xF0383,
    "music":              0xF0389,
    "phone":              0xF03F2,
    "close-box":          0xF0157,
    "speedometer":        0xF04CA,
    "power":              0xF0425,
    "power-plug":         0xF06A5,
    "power-standby":      0xF0426,
    "radiator":           0xF044C,
    "run":                0xF04C8,
    "shield":             0xF0490,
    "shield-home":        0xF08D7,
    "sleep":              0xF04B2,
    "speaker":            0xF04C3,
    "star":               0xF04CE,
    "television":         0xF0502,
    "thermometer":        0xF050F,
    "weather-night":      0xF0594,
    "weather-sunny":      0xF0599,
    "wifi":               0xF05A9,
    "window-open":        0xF0631,
    "robot-vacuum":       0xF09D4,
    "air-conditioner":    0xF0025,
    "garage":             0xF12D5,
    "garage-open":        0xF12D6,
    "ceiling-light":      0xF09D9,
    "skip-previous":      0xF04AE,
    "skip-next":          0xF04AD,
    "play-pause":         0xF03E4,
    "eject":              0xF01F4,
    "monitor":            0xF0379,
    "timer":              0xF0523,
    "timer-sand":         0xF0531,
}

# Icons shown in the picker grid — user-selected set
COMMON_ICONS = [
    "access-point", "alert", "alert-circle",
    "arrow-collapse-all", "arrow-down", "arrow-down-bold",
    "arrow-expand-all", "arrow-left", "arrow-left-bold",
    "arrow-right", "arrow-right-bold", "arrow-up", "arrow-up-bold",
    "battery", "battery-charging", "battery-high", "battery-low",
    "battery-medium", "battery-outline",
    "bell", "bell-off", "bell-ring",
    "bluetooth", "bluetooth-off",
    "bookmark", "bookmark-plus", "bookmark-remove",
    "border-all", "brightness-7",
    "cast", "ceiling-light", "cellphone",
    "chart-areaspline", "chart-bar", "chart-donut",
    "chevron-double-down", "chevron-double-left", "chevron-double-right",
    "chevron-double-up", "chevron-down", "chevron-left", "chevron-right", "chevron-up",
    "clock", "clock-digital",
    "cog", "cog-box",
    "content-copy", "content-cut", "content-paste", "content-save",
    "cursor-default", "cursor-move", "cursor-pointer", "cursor-text",
    "delete-empty", "delete-outline", "desk-lamp", "desk-lamp-on",
    "desktop-tower-monitor",
    "email-open", "email-outline", "ethernet", "expansion-card",
    "file", "file-outline", "flash", "floor-lamp",
    "folder", "folder-multiple", "folder-open",
    "fullscreen", "fullscreen-exit",
    "gauge-empty", "gauge-full",
    "harddisk", "headphones", "heart", "help", "help-circle",
    "home", "home-outline",
    "keyboard",
    "lamp", "led-off", "led-strip", "led-strip-variant",
    "lightbulb", "lightbulb-multiple", "lightbulb-on",
    "message", "message-outline", "message-text", "microphone",
    "monitor", "monitor-cellphone", "monitor-dashboard",
    "monitor-multiple", "monitor-screenshot", "mouse", "music", "music-note",
    "network-outline", "network-strength-1", "network-strength-2",
    "network-strength-3", "network-strength-4",
    "palette", "palette-outline", "palette-swatch",
    "pause", "pin", "pin-outline", "play", "play-pause",
    "power-sleep", "power-socket-uk",
    "radio", "router-wireless",
    "select-inverse", "server",
    "skip-backward", "skip-forward", "skip-next", "skip-previous",
    "speaker", "speedometer", "speedometer-medium", "star", "stop",
    "television-classic", "thermometer", "timer-outline",
    "tooltip-text", "tune", "tune-vertical",
    "usb-flash-drive",
    "volume-high", "volume-medium", "volume-off",
    "wifi", "wifi-off", "window-closed", "wrench",
]


def ensure_assets():
    """Populate built-ins immediately, then download font + meta in background."""
    for name, cp in _BUILTIN.items():
        _codepoints[name] = chr(cp)
    if _META_PATH.exists():
        _load_meta()
    if FONT_PATH.exists():
        ready.set()
        if not _META_PATH.exists():
            threading.Thread(target=_fetch_meta, daemon=True).start()
    else:
        threading.Thread(target=_fetch_all, daemon=True).start()


def _fetch_all():
    global error
    try:
        import requests
        for url, path in [(_FONT_URL, FONT_PATH),
                          (_META_URL, _META_PATH)]:
            r = requests.get(url, timeout=60)
            r.raise_for_status()
            path.write_bytes(r.content)
            if path == _META_PATH:
                _load_meta()
        ready.set()
    except Exception as e:
        error = str(e)
        ready.set()


def _fetch_meta():
    try:
        import requests
        r = requests.get(_META_URL, timeout=60)
        r.raise_for_status()
        _META_PATH.write_bytes(r.content)
        _load_meta()
    except Exception:
        pass


def _load_meta():
    try:
        data = json.loads(_META_PATH.read_text(encoding="utf-8"))
        for item in data:
            name = item.get("name", "")
            cp   = item.get("codepoint", "")
            if name and cp:
                _codepoints[name] = chr(int(cp, 16))
    except Exception:
        pass




def get_char(name: str) -> str | None:
    """Return the Unicode character for an MDI icon name, or None."""
    key = name.lower().replace("mdi:", "").replace("mdi-", "")
    return _codepoints.get(key)


def _get_font(size: int):
    if not FONT_PATH.exists() or not _PIL_OK:
        return None
    if size not in _font_cache:
        try:
            _font_cache[size] = ImageFont.truetype(str(FONT_PATH), size)
        except Exception:
            return None
    return _font_cache[size]


def render(name: str, size: int = 36,
           color: tuple = (255, 255, 255)) -> "Image.Image | None":
    """Render an MDI icon as a PIL RGBA Image, or None if unavailable."""
    if not _PIL_OK or not FONT_PATH.exists():
        return None
    ch = get_char(name)
    if ch is None:
        return None
    font = _get_font(size)
    if font is None:
        return None
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    try:
        bbox = draw.textbbox((0, 0), ch, font=font)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        x  = (size - tw) // 2 - bbox[0]
        y  = (size - th) // 2 - bbox[1]
        rgba = color if len(color) == 4 else (*color, 255)
        draw.text((x, y), ch, font=font, fill=rgba)
    except Exception:
        return None
    return img


def render_tk(name: str, size: int = 36, color: tuple = (255, 255, 255)):
    """Render icon as a Tkinter PhotoImage, or None."""
    if not _PIL_OK:
        return None
    img = render(name, size, color)
    if img is None:
        return None
    return ImageTk.PhotoImage(img)


ensure_assets()
