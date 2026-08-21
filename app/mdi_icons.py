"""Iris 3.0 — MDI Icon Engine & Full 7,440+ Library Indexer.

Provides:
1. Fast glyph rendering for Tkinter and PIL.
2. Full metadata indexing for all 7,440+ icons from MaterialDesignIcons.
3. Sub-millisecond ranked search by name, aliases, brand prefixes, and category tags.
4. Automatic alias resolution (e.g. 'xbox' -> 'microsoft-xbox', 'playstation' -> 'sony-playstation').
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Dict, List, Optional, Any

log = logging.getLogger("iris.mdi_icons")

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

_codepoints: Dict[str, str] = {}
_meta_items: List[Dict[str, Any]] = []
_font_cache: Dict[int, Any] = {}
ready       = threading.Event()
error: str  = ""

# Common brand prefixes to automatically alias
_BRAND_PREFIXES = ["microsoft-", "sony-", "nintendo-", "google-", "apple-"]

# Category mapping from UI pill names to official MDI tags
CATEGORY_TAG_MAP = {
    "home": ["Home Automation", "Hardware / Tools", "Device / Tech", "View"],
    "work": ["Developer / Languages", "Files / Folders", "Account / User", "Communication", "Device / Tech"],
    "gamer": ["Gaming / RPG"],
    "gaming": ["Gaming / RPG"],
    "flight": ["Transportation + Flying", "Science"],
    "hardware": ["Hardware / Tools", "Device / Tech", "Developer / Languages"],
    "rig": ["Hardware / Tools", "Device / Tech"],
    "lifestyle": ["Health / Beauty", "Food / Drink", "Shopping", "Audio", "Music", "Photography", "Transportation + Flying", "Weather"],
    "media": ["Audio", "Music", "Video / Movie", "Photography"],
    "audio": ["Audio", "Music"],
    "system": ["Settings", "Files / Folders", "Security / Lock", "Home Automation", "View", "Device / Tech"],
}

# ── Built-in fallback codepoints (stable across MDI 5–7) ─────────────────────
_BUILTIN = {
    "account":            0xF0004,
    "airplane":           0xF001D,
    "airplane-landing":   0xF05D4,
    "airplane-takeoff":   0xF05D5,
    "alarm":              0xF0020,
    "alarm-light":        0xF0578,
    "alarm-ring":         0xF078A,
    "application":        0xF0614,
    "apps":               0xF003B,
    "arrow-left":         0xF004D,
    "battery-charging":   0xF0080,
    "bell":               0xF004A,
    "bell-off":           0xF1063,
    "bell-ring":          0xF004B,
    "bluetooth":          0xF00AF,
    "border-none-variant":0xF08E4,
    "brightness-5":       0xF0070,
    "brightness-6":       0xF0071,
    "brightness-7":       0xF0072,
    "calculator":         0xF00E0,
    "camera":             0xF0100,
    "car":                0xF00B9,
    "cellphone":          0xF011C,
    "check":              0xF012C,
    "clock":              0xF0950,
    "close":              0xF0156,
    "cog":                0xF0493,
    "cog-outline":        0xF1087,
    "coffee":             0xF00ED,
    "compass":            0xF018A,
    "controller-classic": 0xF0183,
    "cpu-64-bit":         0xF0ED6,
    "crosshairs":         0xF01A3,
    "desktop-mac":        0xF01C4,
    "desktop-tower-monitor": 0xF0A98,
    "door":               0xF081A,
    "eject":              0xF01F4,
    "expansion-card":     0xF08AE,
    "fan":                0xF0210,
    "file":               0xF0214,
    "flash":              0xF0224,
    "folder":             0xF024B,
    "folder-open":        0xF024C,
    "gamepad":            0xF026B,
    "gamepad-variant":    0xF026C,
    "harddisk":           0xF02C2,
    "headphones":         0xF02CB,
    "headset":            0xF02CE,
    "heart":              0xF02D1,
    "help-circle":        0xF02D7,
    "home":               0xF02DC,
    "keyboard":           0xF0312,
    "lamp":               0xF06B5,
    "layers":             0xF0328,
    "led-strip":          0xF1016,
    "lightbulb":          0xF0335,
    "lightning-bolt":     0xF0691,
    "lock":               0xF033E,
    "memory":             0xF035B,
    "microphone":         0xF036C,
    "microphone-off":     0xF036D,
    "microsoft-xbox":     0xF05B9,
    "microsoft-xbox-controller": 0xF05BA,
    "monitor":            0xF0379,
    "mouse":              0xF037D,
    "movie":              0xF0383,
    "music":              0xF0389,
    "palette":            0xF03D8,
    "play-pause":         0xF03E4,
    "plus":               0xF0415,
    "power":              0xF0425,
    "radar":              0xF0437,
    "radiator":           0xF044C,
    "rocket-launch":      0xF1019,
    "shield":             0xF0490,
    "shield-airplane":    0xF18AE,
    "skip-next":          0xF04AD,
    "skip-previous":      0xF04AE,
    "sony-playstation":   0xF05B3,
    "speaker":            0xF04C3,
    "speedometer":        0xF04CA,
    "star":               0xF04CE,
    "sword":              0xF04E5,
    "sync":               0xF04E6,
    "target":             0xF04F1,
    "timer":              0xF0523,
    "tune":               0xF0552,
    "volume-high":        0xF057E,
    "volume-medium":      0xF057F,
    "volume-off":         0xF0581,
    "wifi":               0xF05A9,
}


def _load_meta():
    """Load and index all 7,440+ icons with aliases and categories."""
    global _meta_items
    if not _META_PATH.exists():
        return
    try:
        data = json.loads(_META_PATH.read_text(encoding="utf-8"))
        _meta_items = []
        for item in data:
            name = (item.get("name") or "").strip()
            cp   = (item.get("codepoint") or "").strip()
            if not name or not cp:
                continue
            char = chr(int(cp, 16))
            aliases = [a.lower().strip() for a in item.get("aliases", []) if a]
            tags = item.get("tags", [])

            _meta_items.append({
                "name": name,
                "char": char,
                "codepoint": cp,
                "aliases": aliases,
                "tags": tags,
            })

            # Primary mapping
            _codepoints[name.lower()] = char

            # Alias mapping
            for alias in aliases:
                _codepoints[alias] = char

            # Auto-strip brand prefixes (e.g. microsoft-xbox -> xbox)
            for pfx in _BRAND_PREFIXES:
                if name.startswith(pfx):
                    short_name = name[len(pfx):]
                    if short_name not in _codepoints:
                        _codepoints[short_name] = char
        log.info("[mdi] Indexed %d icons and aliases from meta.json", len(_meta_items))
    except Exception as ex:
        log.warning("[mdi] Failed to load meta.json: %s", ex)


def ensure_assets():
    """Populate built-ins immediately, then load or fetch full library in background."""
    for name, cp in _BUILTIN.items():
        ch = chr(cp)
        _codepoints[name] = ch
        for pfx in _BRAND_PREFIXES:
            if name.startswith(pfx):
                _codepoints[name[len(pfx):]] = ch

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
        for url, path in [(_FONT_URL, FONT_PATH), (_META_URL, _META_PATH)]:
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


def get_char(name: str) -> Optional[str]:
    """Return the Unicode character for an MDI icon name/alias, or None."""
    if not name:
        return None
    key = name.lower().strip().replace("mdi:", "").replace("mdi-", "")
    if key in _codepoints:
        return _codepoints[key]

    # Try matching brand prefix fallbacks
    for pfx in _BRAND_PREFIXES:
        if (pfx + key) in _codepoints:
            return _codepoints[pfx + key]

    return None


def search_icons(query: str = "", category: str = "", limit: int = 120) -> List[Dict[str, Any]]:
    """Ranked search across all 7,440+ icons by name, aliases, and category tags."""
    q = (query or "").lower().strip().replace("mdi:", "").replace("mdi-", "")
    cat = (category or "").lower().strip()
    target_tags = CATEGORY_TAG_MAP.get(cat, [cat] if cat and cat != "all" else [])

    results = []
    for item in _meta_items:
        name = item["name"]
        aliases = item["aliases"]
        tags = item["tags"]

        # Category filter check
        if target_tags:
            if not any(t.lower() in [tag.lower() for tag in tags] for t in target_tags):
                # Also check name/aliases if category matches as a keyword
                if not any(t.lower() in name or any(t.lower() in a for a in aliases) for t in target_tags):
                    continue

        if not q:
            # Browsing category without search query
            results.append((10, item))
            continue

        # Scoring
        score = 0
        if name == q:
            score = 100
        elif name.startswith(q):
            score = 85
        elif f"-{q}" in name:
            score = 70
        elif q in name:
            score = 60
        elif any(a == q for a in aliases):
            score = 75
        elif any(a.startswith(q) for a in aliases):
            score = 65
        elif any(q in a for a in aliases):
            score = 50
        elif any(q in t.lower() for t in tags):
            score = 30

        if score > 0:
            results.append((score, item))

    # Sort by score descending, then by name length / alpha
    results.sort(key=lambda x: (-x[0], len(x[1]["name"]), x[1]["name"]))

    out = []
    for _, item in results[:limit]:
        out.append({
            "name": item["name"],
            "char": item["char"],
            "aliases": item["aliases"],
            "tags": item["tags"],
        })
    return out


def _get_font(size: int):
    if not FONT_PATH.exists() or not _PIL_OK:
        return None
    if size not in _font_cache:
        try:
            _font_cache[size] = ImageFont.truetype(str(FONT_PATH), size)
        except Exception:
            return None
    return _font_cache[size]


def render(name: str, size: int = 36, color: tuple = (255, 255, 255)) -> Optional["Image.Image"]:
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
