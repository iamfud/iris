"""Iris — Tray icon and static menu."""

import logging
import sys
from pathlib import Path
import pystray
from PIL import Image
from constants import TRAY_ICON_SIZE

log = logging.getLogger("iris.tray")

_ICON_CACHE = {}

if getattr(sys, "frozen", False):
    _MEDIA_DIR = Path(sys._MEIPASS) / "media"
else:
    _MEDIA_DIR = Path(__file__).resolve().parent.parent / "media"


def make_icon_image(size=TRAY_ICON_SIZE, online=False):
    key = (size, online)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]

    src = _MEDIA_DIR / "Iris_full.png"
    if not src.exists():
        src = _MEDIA_DIR / "Iris_128.png"
    if not src.exists():
        src = _MEDIA_DIR / "Iris_256.png"

    if src.exists():
        img = Image.open(src).convert("RGBA")
        if img.size != (size, size):
            img = img.resize((size, size), Image.LANCZOS)
    else:
        log.warning("No tray icon file found in %s", _MEDIA_DIR)
        img = Image.new("RGBA", (size, size), (0, 0, 0, 0))

    _ICON_CACHE[key] = img
    return img


def build_tray_menu(app):
    return pystray.Menu(
        pystray.MenuItem(
            "Show/Hide Panel",
            lambda *a: app._on_tray_click(),
            default=True,
        ),
        pystray.MenuItem(
            "Quick Actions Toolbar",
            lambda *a: app._open_capture_toolbar(),
        ),
        pystray.MenuItem(
            "Iris Settings",
            lambda *a: app._open_settings(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Stopwatch",
            lambda *a: app._toggle_stopwatch(),
        ),
        pystray.MenuItem(
            "Countdown Timer",
            lambda *a: app._toggle_countdown(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(
            "Quit Iris",
            lambda *a: app._quit(),
        ),
    )
