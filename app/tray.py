"""Iris — Tray icon and static menu."""

import logging
import pystray
from PIL import Image, ImageDraw

log = logging.getLogger("iris.tray")

_ICON_CACHE = {}


def make_icon_image(size=64, online=False):
    key = (size, online)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(
        [2, 2, size - 2, size - 2], radius=8, fill=(72, 178, 233, 255)
    )
    d.rectangle(
        [size // 4, size // 4, size // 2, size * 3 // 4], fill=(0, 0, 0, 0)
    )
    d.arc(
        [size // 4, size // 4, size * 3 // 4, size * 3 // 4], -90, 90,
        fill=(72, 178, 233, 255), width=max(2, size // 12),
    )
    if online:
        r = max(3, size // 9)
        d.ellipse(
            [size - r * 2 - 1, size - r * 2 - 1, size - 1, size - 1],
            fill=(0, 255, 100, 255),
        )
    _ICON_CACHE[key] = img
    return img


def build_tray_menu(app):
    return pystray.Menu(
        pystray.MenuItem(
            "Iris Settings",
            lambda *a: app._open_settings(),
            default=True,
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
