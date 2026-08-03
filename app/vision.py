"""Vision — reusable screen analysis engine.

Generic screen capture and measurement primitives used by the Vision
plugin.  This module has **no game logic** — it only knows about
monitors, regions, pixels, and colours.  All units for stored regions
are percentages of the display they were captured on, so a region stays
on-target if the display layout is unchanged.

Public API
----------
- ``virtual_screen_bounds()`` / ``monitor_rects()`` / ``monitor_containing()``
- ``resolve_exe_for_point(x, y)`` — exe name under a screen point
- ``region_to_bbox()`` / ``region_to_pct()`` — anchor <-> percentage math
- ``capture(bbox)`` / ``screenshot_b64(bbox)`` — screen grabbing
- ``measure(draft)`` — run one measurement against a sensor draft
- ``RegionSelector`` / ``select_region(root, timeout)`` — calibration UI
"""

import base64
import ctypes
import io
import logging
import math
import os
import threading
import time
import tkinter as tk

from ctypes import wintypes

log = logging.getLogger("iris.vision")

_MAX_SAMPLES = 4000


# ── Monitor geometry ───────────────────────────────────────────

def virtual_screen_bounds():
    """Return (x, y, width, height) of the virtual screen across all monitors."""
    try:
        user32 = ctypes.windll.user32
        return (
            user32.GetSystemMetrics(76),  # SM_XVIRTUALSCREEN
            user32.GetSystemMetrics(77),  # SM_YVIRTUALSCREEN
            user32.GetSystemMetrics(78),  # SM_CXVIRTUALSCREEN
            user32.GetSystemMetrics(79),  # SM_CYVIRTUALSCREEN
        )
    except Exception:
        return (0, 0, 1920, 1080)


_MONITORENUMPROC = ctypes.WINFUNCTYPE(
    ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p,
    ctypes.POINTER(wintypes.RECT), ctypes.c_void_p)


def monitor_rects():
    """Return list of {x, y, w, h} rects, one per monitor (virtual coords)."""
    rects = []

    def _cb(_hmon, _hdc, lprc, _data):
        r = lprc.contents
        rects.append({
            "x": r.left,
            "y": r.top,
            "w": r.right - r.left,
            "h": r.bottom - r.top,
        })
        return True

    try:
        ctypes.windll.user32.EnumDisplayMonitors(None, None, _MONITORENUMPROC(_cb), 0)
    except Exception:
        x, y, w, h = virtual_screen_bounds()
        rects = [{"x": x, "y": y, "w": w, "h": h}]
    return rects


def monitor_containing(x, y):
    """Return the monitor rect dict that contains point (x, y)."""
    for m in monitor_rects():
        if m["x"] <= x < m["x"] + m["w"] and m["y"] <= y < m["y"] + m["h"]:
            return m
    x0, y0, w, h = virtual_screen_bounds()
    return {"x": x0, "y": y0, "w": w, "h": h}


def resolve_exe_for_point(x, y):
    """Return the exe filename of the top-level window under (x, y)."""
    try:
        user32 = ctypes.windll.user32
        point = wintypes.POINT(int(x), int(y))
        hwnd = user32.WindowFromPoint(point)
        if not hwnd:
            return ""
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ""
        import psutil
        return os.path.basename(psutil.Process(pid.value).exe())
    except Exception:
        return ""


# ── Region math ────────────────────────────────────────────────

def region_to_bbox(anchor, region):
    """Convert an anchor rect + percentage region to a pixel bbox.

    Returns (left, top, right, bottom) in virtual screen coordinates.
    """
    ax, ay, aw, ah = anchor["x"], anchor["y"], anchor["w"], anchor["h"]
    x = int(ax + (region.get("x_pct", 0) / 100.0) * aw)
    y = int(ay + (region.get("y_pct", 0) / 100.0) * ah)
    w = int((region.get("w_pct", 100) / 100.0) * aw)
    h = int((region.get("h_pct", 100) / 100.0) * ah)
    return (x, y, max(x + w, x + 1), max(y + h, y + 1))


def region_to_pct(anchor, rect):
    """Convert a pixel rect (x, y, w, h) into percentages of *anchor*."""
    ax, ay, aw, ah = anchor["x"], anchor["y"], anchor["w"], anchor["h"]
    x, y, w, h = rect
    if aw <= 0 or ah <= 0:
        return {"x_pct": 0, "y_pct": 0, "w_pct": 100, "h_pct": 100}
    return {
        "x_pct": round((x - ax) / aw * 100.0, 2),
        "y_pct": round((y - ay) / ah * 100.0, 2),
        "w_pct": round(w / aw * 100.0, 2),
        "h_pct": round(h / ah * 100.0, 2),
    }


def default_anchor():
    x, y, w, h = virtual_screen_bounds()
    return {"x": x, "y": y, "w": w, "h": h}


def normalize_draft(draft):
    """Fill any missing measurement fields with sensible defaults."""
    d = dict(draft or {})
    d.setdefault("mode", "color_percentage")
    d.setdefault("anchor", default_anchor())
    if not d.get("region"):
        d["region"] = {"x_pct": 0, "y_pct": 0, "w_pct": 100, "h_pct": 100}
    d.setdefault("color", "#ff0000")
    d.setdefault("pixel", {"x_pct": 50, "y_pct": 50})
    d.setdefault("tolerance", 40)
    d.setdefault("threshold", 30.0)
    d.setdefault("direction", "below")
    d.setdefault("require_foreground", False)
    return d


# ── Capture ────────────────────────────────────────────────────

def capture(bbox):
    """Grab the screen region and return a PIL RGB image."""
    from PIL import ImageGrab
    img = ImageGrab.grab(bbox=bbox)
    return img.convert("RGB")


def screenshot_b64(bbox):
    """Grab the region and return a base64-encoded PNG."""
    img = capture(bbox)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


# ── Measurement ────────────────────────────────────────────────

def _hex_to_rgb(hex_str):
    c = (hex_str or "#ff0000").lstrip("#")
    if len(c) != 6:
        return (255, 0, 0)
    try:
        return (int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16))
    except ValueError:
        return (255, 0, 0)


def _rgb_dist(p, q):
    return math.sqrt(
        (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 + (p[2] - q[2]) ** 2)


def _luma(p):
    return 0.2126 * p[0] + 0.7152 * p[1] + 0.0722 * p[2]


def _sample(data, total):
    """Return a strided sample of pixel tuples (max ~_MAX_SAMPLES)."""
    if total <= _MAX_SAMPLES:
        return data
    step = math.ceil(total / _MAX_SAMPLES)
    return data[::step]


def measure(draft):
    """Run one measurement against a sensor *draft*.

    Returns ``{"value", "active", "mode", "sampled"}``.  Stateless —
    never touches the exe gate, so it works even when the app is
    closed (used by the wizard's Test step).
    """
    d = normalize_draft(draft)
    mode = d.get("mode", "color_percentage")
    anchor = d.get("anchor")
    region = d.get("region")
    if not anchor or not region:
        return {"value": 0.0, "active": False, "mode": mode, "sampled": 0}

    bbox = region_to_bbox(anchor, region)
    if bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
        return {"value": 0.0, "active": False, "mode": mode, "sampled": 0}

    try:
        img = capture(bbox)
    except Exception:
        log.warning("vision capture failed", exc_info=True)
        return {"value": 0.0, "active": False, "mode": mode, "sampled": 0}

    w, h = img.size
    if w <= 0 or h <= 0:
        return {"value": 0.0, "active": False, "mode": mode, "sampled": 0}

    if mode == "pixel_match":
        px = d.get("pixel", {})
        px_x = int(px.get("x_pct", 50) / 100.0 * w)
        px_y = int(px.get("y_pct", 50) / 100.0 * h)
        px_x = min(max(px_x, 0), w - 1)
        px_y = min(max(px_y, 0), h - 1)
        target = _hex_to_rgb(d.get("color"))
        tol = d.get("tolerance", 40)
        sample_px = img.getpixel((px_x, px_y))
        value = 100.0 if _rgb_dist(sample_px, target) <= tol else 0.0
        sampled = 1
    else:
        data = list(img.getdata())
        pixels = _sample(data, len(data))
        sampled = len(pixels)
        if mode == "color_percentage":
            target = _hex_to_rgb(d.get("color"))
            tol = d.get("tolerance", 40)
            count = 0
            for p in pixels:
                if _rgb_dist(p, target) <= tol:
                    count += 1
            value = count / sampled * 100.0 if sampled else 0.0
        else:  # average_brightness
            value = sum(_luma(p) for p in pixels) / sampled if sampled else 0.0

    threshold = d.get("threshold", 30.0)
    if d.get("direction", "below") == "above":
        active = value > threshold
    elif mode == "color_percentage":
        # "below" for colour % means the colour is present but scarce.
        # A value of 0 (colour absent, e.g. a menu that doesn't draw the
        # target UI element) must NOT trigger.
        active = 0 < value < threshold
    else:
        active = value < threshold

    return {
        "value": round(value, 2),
        "active": bool(active),
        "mode": mode,
        "sampled": sampled,
    }


# ── Region selector UI ─────────────────────────────────────────

class RegionSelector:
    """Fullscreen dim overlay where the user drags out a region.

    Runs on the Tk main thread.  ``on_done`` is called with
    ``(x, y, w, h)`` in virtual screen coordinates when the user
    releases the drag, or with ``None`` when cancelled (Escape).
    """

    def __init__(self, root, on_done):
        self._root = root
        self._on_done = on_done
        self._start = None
        self._rect_id = None

        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.configure(bg="black")
        self._win.attributes("-alpha", 0.3)

        x, y, w, h = virtual_screen_bounds()
        self._win.geometry(f"{w}x{h}+{x}+{y}")
        self._win.lift()

        self._canvas = tk.Canvas(
            self._win, bg="black", highlightthickness=0, cursor="crosshair")
        self._canvas.pack(fill="both", expand=True)

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Escape>", self._on_escape)
        self._win.bind("<Escape>", self._on_escape)
        self._win.focus_force()
        self._canvas.focus_set()

    def show(self):
        self._win.deiconify()
        self._win.attributes("-topmost", True)
        self._win.lift()
        self._win.focus_force()

    def close(self, result):
        try:
            self._win.destroy()
        except Exception:
            pass
        self._on_done(result)

    def _on_press(self, event):
        self._start = (event.x_root, event.y_root)
        self._rect_id = self._canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#48B2E9", width=2, fill="", dash=(6, 3))

    def _on_drag(self, event):
        if self._start is None:
            return
        self._canvas.coords(
            self._rect_id, self._start[0], self._start[1], event.x_root, event.y_root)

    def _on_release(self, event):
        if self._start is None:
            return
        x0, y0 = self._start
        x1, y1 = event.x_root, event.y_root
        x, y = min(x0, x1), min(y0, y1)
        w = abs(x1 - x0)
        h = abs(y1 - y0)
        if w < 8 or h < 8:
            self.close(None)
            return
        self.close((x, y, w, h))

    def _on_escape(self, _event):
        self.close(None)


def select_region(root, timeout=60):
    """Open the region selector on the Tk main thread and block.

    Marshals the overlay onto the Tk main thread via ``root.after``;
    the calling (HTTP) thread blocks on a ``threading.Event`` so the
    mainloop keeps running.  Returns ``(x, y, w, h)`` or ``None``.
    """
    if root is None:
        return None
    done = threading.Event()
    holder = {}

    def _open():
        try:
            def _done(rect):
                holder["rect"] = rect
                done.set()
            sel = RegionSelector(root, _done)
            sel.show()
        except Exception:
            log.warning("failed to open region selector", exc_info=True)
            done.set()

    try:
        root.after(0, _open)
    except Exception:
        return None

    if not done.wait(timeout):
        return None
    return holder.get("rect")
