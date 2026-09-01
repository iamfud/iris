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
import re
import threading
import time
import tkinter as tk

from ctypes import wintypes
from win_platform import init_dpi_awareness

log = logging.getLogger("iris.vision")

init_dpi_awareness()

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

    Returns (left, top, right, bottom) in virtual screen coordinates,
    always clamped to the virtual screen and at least 1x1, so a capture can
    never exceed a full-screen grab no matter what anchor/region values the
    runtime is given.
    """
    anchor = anchor if isinstance(anchor, dict) else {}
    region = region if isinstance(region, dict) else {}
    try:
        ax = float(anchor.get("x", 0))
        ay = float(anchor.get("y", 0))
        aw = float(anchor.get("w", 0))
        ah = float(anchor.get("h", 0))
    except (TypeError, ValueError):
        ax = ay = 0.0
        aw = ah = 0.0
    if not all(math.isfinite(v) for v in (ax, ay, aw, ah)) or aw <= 0 or ah <= 0:
        ax, ay, aw, ah = 0.0, 0.0, 1920.0, 1080.0

    def _pct(key, default):
        try:
            v = float(region.get(key, default))
        except (TypeError, ValueError):
            return default
        return v if math.isfinite(v) else default

    x_pct = _pct("x_pct", 0.0)
    y_pct = _pct("y_pct", 0.0)
    w_pct = _pct("w_pct", 100.0)
    h_pct = _pct("h_pct", 100.0)

    left = int(ax + (x_pct / 100.0) * aw)
    top = int(ay + (y_pct / 100.0) * ah)
    right = int(left + max((w_pct / 100.0) * aw, 1.0))
    bottom = int(top + max((h_pct / 100.0) * ah, 1.0))

    vx, vy, vw, vh = virtual_screen_bounds()
    v_right = vx + vw
    v_bottom = vy + vh
    # Clamp both edges.  Clamping only the lower bound leaves ``left`` or
    # ``top`` beyond the virtual display when a malformed region starts past
    # its far edge, producing an inverted PIL bounding box.
    left = max(vx, min(left, v_right - 1))
    top = max(vy, min(top, v_bottom - 1))
    right = min(right, v_right)
    bottom = min(bottom, v_bottom)
    if right <= left:
        right = min(left + 1, v_right)
    if bottom <= top:
        bottom = min(top + 1, v_bottom)
    return (left, top, right, bottom)


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
    d.setdefault("ocr_pattern", "")
    d.setdefault("ocr_match_type", "contains")
    d.setdefault("ocr_case_sensitive", False)
    return d


_SENSOR_MODES = {"color_percentage", "pixel_match", "average_brightness", "ocr_text", "ocr_number"}
_SENSOR_DIRECTIONS = {"above", "below", "equal"}
_OCR_MATCH_TYPES = {"contains", "exact", "regex"}
_SENSOR_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_SENSOR_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def _bool_strict(v, default=False):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "1", "yes", "on"):
            return True
        if s in ("false", "0", "no", "off"):
            return False
    return default


def _float_clamped(v, default, lo, hi):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if not math.isfinite(f):
        return default
    return max(lo, min(hi, f))


def _int_clamped(v, default, lo, hi):
    try:
        f = float(v)
        i = int(f)
    except (TypeError, ValueError, OverflowError):
        return default
    if not math.isfinite(f):
        return default
    return max(lo, min(hi, i))


def _region_sanitized(raw):
    default = {"x_pct": 0.0, "y_pct": 0.0, "w_pct": 100.0, "h_pct": 100.0}
    if not isinstance(raw, dict):
        return default
    return {
        "x_pct": _float_clamped(raw.get("x_pct"), default["x_pct"], -1000.0, 1000.0),
        "y_pct": _float_clamped(raw.get("y_pct"), default["y_pct"], -1000.0, 1000.0),
        "w_pct": _float_clamped(raw.get("w_pct"), default["w_pct"], 0.0, 1000.0),
        "h_pct": _float_clamped(raw.get("h_pct"), default["h_pct"], 0.0, 1000.0),
    }


def _pixel_sanitized(raw):
    default = {"x_pct": 50.0, "y_pct": 50.0}
    if not isinstance(raw, dict):
        return default
    return {
        "x_pct": _float_clamped(raw.get("x_pct"), default["x_pct"], 0.0, 100.0),
        "y_pct": _float_clamped(raw.get("y_pct"), default["y_pct"], 0.0, 100.0),
    }


def _anchor_sanitized(raw):
    if not isinstance(raw, dict):
        return default_anchor()
    try:
        x = float(raw.get("x", 0))
        y = float(raw.get("y", 0))
        w = float(raw.get("w", 0))
        h = float(raw.get("h", 0))
    except (TypeError, ValueError):
        return default_anchor()
    if not all(math.isfinite(v) for v in (x, y, w, h)):
        return default_anchor()
    return {
        "x": int(max(-32767.0, min(32767.0, x))),
        "y": int(max(-32767.0, min(32767.0, y))),
        "w": int(max(1.0, min(32767.0, w))),
        "h": int(max(1.0, min(32767.0, h))),
    }


def sanitize_sensor(raw):
    """Return a validated, clamped copy of a vision sensor config.

    Unknown keys are dropped and every persisted field is type-coerced and
    clamped to a safe range, so untrusted HTTP input can never produce
    extreme screen captures or crash the per-sensor worker threads.
    """
    raw = raw if isinstance(raw, dict) else {}
    out = {}

    _id = raw.get("id")
    if isinstance(_id, str) and _SENSOR_ID_RE.match(_id):
        out["id"] = _id

    def _text(key, limit=120):
        v = raw.get(key)
        if isinstance(v, str):
            return v.strip()[:limit]
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return str(v)[:limit]
        return ""

    out["name"] = _text("name")
    out["exe"] = _text("exe")
    out["event_name"] = _text("event_name")
    out["event_message"] = _text("event_message", limit=200)

    out["enabled"] = _bool_strict(raw.get("enabled"), True)
    out["output_display"] = _bool_strict(raw.get("output_display"), True)
    out["flash_name"] = _bool_strict(raw.get("flash_name"), False)
    out["play_sound"] = _bool_strict(raw.get("play_sound"), False)
    out["require_foreground"] = _bool_strict(raw.get("require_foreground"), False)

    mode = raw.get("mode")
    out["mode"] = mode if mode in _SENSOR_MODES else "color_percentage"

    direction = raw.get("direction")
    out["direction"] = direction if direction in _SENSOR_DIRECTIONS else "below"

    color = raw.get("color")
    out["color"] = color if (isinstance(color, str) and _SENSOR_COLOR_RE.match(color)) else "#ff0000"

    out["tolerance"] = _int_clamped(raw.get("tolerance"), 40, 0, 255)
    # Colour percentage and pixel-match are percentages; brightness is an
    # 8-bit luminance value.
    threshold_max = 255.0 if out["mode"] == "average_brightness" else 100.0
    out["threshold"] = _float_clamped(raw.get("threshold"), 30.0, 0.0, threshold_max)
    out["poll_rate"] = _float_clamped(raw.get("poll_rate"), 1.0, 0.1, 10.0)
    out["cooldown_s"] = _float_clamped(raw.get("cooldown_s"), 10.0, 0.0, 86400.0)

    out["pixel"] = _pixel_sanitized(raw.get("pixel"))
    out["region"] = _region_sanitized(raw.get("region"))
    out["anchor"] = _anchor_sanitized(raw.get("anchor"))

    out["ocr_pattern"] = _text("ocr_pattern", limit=120)
    match_type = raw.get("ocr_match_type")
    out["ocr_match_type"] = match_type if match_type in _OCR_MATCH_TYPES else "contains"
    out["ocr_case_sensitive"] = _bool_strict(raw.get("ocr_case_sensitive"), False)

    created = raw.get("created")
    if (isinstance(created, (int, float)) and not isinstance(created, bool)
            and math.isfinite(float(created)) and float(created) > 0):
        out["created"] = int(created)
    else:
        out["created"] = int(time.time())

    return out


# ── Capture ────────────────────────────────────────────────────

def capture(bbox):
    """Grab the screen region and return a PIL RGB image."""
    x1, y1, x2, y2 = bbox
    x = int(min(x1, x2))
    y = int(min(y1, y2))
    w = int(abs(x2 - x1))
    h = int(abs(y2 - y1))
    if w <= 0 or h <= 0:
        from PIL import Image
        return Image.new("RGB", (max(1, w), max(1, h)), (0, 0, 0))

    try:
        from PIL import Image
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        hdc_screen = user32.GetDC(None)
        if not hdc_screen:
            raise RuntimeError("GetDC failed")
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        hbm = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
        gdi32.SelectObject(hdc_mem, hbm)

        # 0x00CC0020 is SRCCOPY, 0x40000000 is CAPTUREBLT (includes layered / transparent windows)
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, x, y, 0x00CC0020 | 0x40000000)

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", ctypes.c_long),
                ("biHeight", ctypes.c_long),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", ctypes.c_long),
                ("biYPelsPerMeter", ctypes.c_long),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h  # top-down DIB
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0  # BI_RGB

        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(hdc_mem, hbm, 0, h, buf, ctypes.byref(bmi), 0)

        # Clean up GDI handles
        gdi32.DeleteObject(hbm)
        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(None, hdc_screen)

        return Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).convert("RGB")
    except Exception as exc:
        log.warning("GDI screen capture failed: %s, falling back to ImageGrab", exc)
        try:
            from PIL import ImageGrab
            return ImageGrab.grab(bbox=bbox).convert("RGB")
        except Exception:
            from PIL import Image
            return Image.new("RGB", (w, h), (0, 0, 0))


def screenshot_b64(bbox):
    """Grab the region and return a base64-encoded PNG."""
    img = capture(bbox)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def capture_active_monitor():
    """Capture the physical monitor containing the cursor without stealing window focus."""
    try:
        user32 = ctypes.windll.user32
        pt = wintypes.POINT()
        user32.GetCursorPos(ctypes.byref(pt))
        m = monitor_containing(pt.x, pt.y)
    except Exception:
        x, y, w, h = virtual_screen_bounds()
        m = {"x": x, "y": y, "w": w, "h": h}
    bbox = (m["x"], m["y"], m["x"] + m["w"], m["y"] + m["h"])
    img = capture(bbox)
    return img, m


# ── Windows Native OCR ─────────────────────────────────────────

_ocr_engine = None
_ocr_lock = threading.Lock()

def get_ocr_engine():
    global _ocr_engine
    if _ocr_engine is None:
        try:
            import winrt.windows.media.ocr as ocr
            _ocr_engine = ocr.OcrEngine.try_create_from_user_profile_languages()
            if not _ocr_engine:
                log.warning("No OCR language found in user profile; OCR disabled")
                _ocr_engine = False
        except Exception as ex:
            log.warning("Failed to initialize Windows.Media.Ocr: %s", ex)
            _ocr_engine = False
    return _ocr_engine if _ocr_engine is not False else None


async def _ocr_async(raw_bytes):
    engine = get_ocr_engine()
    if not engine:
        return {"text": "", "lines": [], "words": []}
    try:
        import winrt.windows.graphics.imaging as imaging
        import winrt.windows.storage.streams as streams

        writer = streams.DataWriter()
        writer.write_bytes(raw_bytes)
        ibuffer = writer.detach_buffer()
        stream = streams.InMemoryRandomAccessStream()
        await stream.write_async(ibuffer)
        stream.seek(0)
        decoder = await imaging.BitmapDecoder.create_async(stream)
        software_bitmap = await decoder.get_software_bitmap_async()
        with _ocr_lock:
            res = await engine.recognize_async(software_bitmap)

        words = []
        lines = []
        for line in res.lines:
            lines.append(line.text)
            for word in line.words:
                words.append({
                    "text": word.text,
                    "box": [word.bounding_rect.x, word.bounding_rect.y, word.bounding_rect.width, word.bounding_rect.height]
                })
        return {"text": (res.text or "").strip(), "lines": lines, "words": words}
    except Exception as ex:
        log.warning("OCR recognition failed: %s", ex)
        return {"text": "", "lines": [], "words": []}


def clean_ocr_text(text):
    """Clean up common OCR glyph collisions, punctuation distortions, and font ambiguities in English text."""
    if not text or not isinstance(text, str):
        return text or ""

    import re

    # 1. Normalize stylized / smart quotes and apostrophes
    s = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"').replace("`", "'")

    # 2. Fix standalone '1m' or 'l'm' / '1'm' / '1 m' -> "I'm"
    s = re.sub(r'\b[1l]\s*[\'’]?m\b', "I'm", s)

    # 3. Fix "1" / "l" representing uppercase "I" in common pronouns and contractions
    s = re.sub(r'\b[1l]\s*[\'’]ve\b', "I've", s)
    s = re.sub(r'\b[1l]\s*[\'’]ll\b', "I'll", s)
    s = re.sub(r'\b[1l]\s*[\'’]d\b', "I'd", s)

    # 4. Common contraction fixes where apostrophes were dropped or digits inserted
    s = re.sub(r'\b(don|can|won|didn|isn|aren|wasn|weren|haven|hasn|hadn|wouldn|couldn|shouldn)t\b', r"\1't", s, flags=re.IGNORECASE)
    s = re.sub(r'\b(that|what|here|there|where|who|how)s\b', r"\1's", s, flags=re.IGNORECASE)
    s = re.sub(r'\b1t[\'’]?s\b', "It's", s)
    s = re.sub(r'\blt[\'’]?s\b', "It's", s)

    # 5. Fix standalone "1" / "l" before common English verbs/words
    s = re.sub(
        r'\b[1l]\b(?=\s+(?:think|see|know|was|have|am|would|will|had|got|need|can|could|feel|want|hope|mean|said|did|do|went|guess|thought|only|also|just|love|like|hate|wish|told|found|made)\b)',
        "I", s, flags=re.IGNORECASE
    )

    # 6. Fix isolated single-letter lowercase "i" or digit "1" at start of line/sentence
    s = re.sub(r'(?:^|(?<=[\.\?\!\n]\s))[1l]\b', "I", s)

    # 7. Clean up redundant spaces around punctuation
    s = re.sub(r'\s+([,\.\?!;:])', r'\1', s)
    s = re.sub(r'([\({\[])\s+', r'\1', s)
    s = re.sub(r'\s+([\)\]}])', r'\1', s)

    return s.strip()


def ocr_extract(img, clean=True):
    """Run native Windows OCR on a PIL image and return recognized text and word boxes."""
    if img is None:
        return {"text": "", "lines": [], "words": []}
    try:
        from PIL import ImageOps, ImageEnhance, Image

        w, h = img.size
        if w <= 0 or h <= 0:
            return {"text": "", "lines": [], "words": []}

        # 1. Target height scaling: Windows.Media.Ocr fails on small text (< 30px glyphs).
        # Upscaling tight HUD crops to ~140px height dramatically improves character recognition.
        scale = max(1.0, 140.0 / float(h))
        if scale > 1.0:
            nw = max(60, int(w * scale))
            nh = max(60, int(h * scale))
            proc_img = img.resize((nw, nh), Image.Resampling.BILINEAR)
        else:
            proc_img = img

        # 2. Quiet border padding: OCR engines require breathing room around edge characters.
        bg_sample = proc_img.getpixel((0, 0))
        if isinstance(bg_sample, int):
            bg_color = (bg_sample, bg_sample, bg_sample)
        else:
            bg_color = bg_sample[:3]
        padded = ImageOps.expand(proc_img, border=18, fill=bg_color)

        # 3. Contrast enhancement
        enhancer = ImageEnhance.Contrast(padded)
        enhanced = enhancer.enhance(1.4)

        import asyncio
        buf = io.BytesIO()
        enhanced.save(buf, format="BMP")
        raw_bytes = buf.getvalue()
        res = asyncio.run(_ocr_async(raw_bytes))

        # Pass 2 Fallback: if initial pass found nothing, try auto-contrasted grayscale
        if not res.get("text"):
            gray = ImageOps.autocontrast(padded.convert("L")).convert("RGB")
            buf2 = io.BytesIO()
            gray.save(buf2, format="BMP")
            res = asyncio.run(_ocr_async(buf2.getvalue()))

        if clean and res.get("text"):
            res["text"] = clean_ocr_text(res["text"])
            for line in res.get("lines", []):
                if "text" in line:
                    line["text"] = clean_ocr_text(line["text"])

        return res
    except Exception as ex:
        log.warning("ocr_extract error: %s", ex)
        return {"text": "", "lines": [], "words": []}


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

    Returns ``{"value", "active", "mode", "sampled", ...}``. Stateless —
    never touches the exe gate, so it works even when the app is
    closed (used by the wizard's Test step).
    """
    d = draft if (isinstance(draft, dict) and draft.get("_sanitized")) else sanitize_sensor(draft)
    mode = d.get("mode", "color_percentage")
    anchor = d.get("anchor")
    region = d.get("region")
    if not anchor or not region:
        return {"value": 0.0, "active": False, "mode": mode, "sampled": 0}

    bbox = d.get("_bbox") or region_to_bbox(anchor, region)
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

    if mode == "ocr_text":
        ocr_res = ocr_extract(img)
        text = ocr_res.get("text", "")
        pattern = (d.get("ocr_pattern") or "").strip()
        match_type = d.get("ocr_match_type", "contains")
        case_sensitive = d.get("ocr_case_sensitive", False)

        is_match = False
        if pattern:
            target = pattern if case_sensitive else pattern.lower()
            candidate = text if case_sensitive else text.lower()
            if match_type == "exact":
                is_match = (candidate == target)
            elif match_type == "regex":
                try:
                    flags = 0 if case_sensitive else re.IGNORECASE
                    is_match = bool(re.search(pattern, text, flags))
                except re.error:
                    is_match = False
            else:  # contains
                is_match = (target in candidate)

        return {
            "value": text,
            "text": text,
            "active": bool(is_match),
            "mode": mode,
            "sampled": 1,
            "words": ocr_res.get("words", []),
        }

    if mode == "ocr_number":
        ocr_res = ocr_extract(img)
        text = ocr_res.get("text", "")
        match = re.search(r"[-+]?\d+(?:\.\d+)?", text)
        if match:
            try:
                num_val = float(match.group(0))
            except ValueError:
                num_val = 0.0
        else:
            num_val = 0.0

        threshold = float(d.get("threshold", 30.0))
        direction = d.get("direction", "below")
        if direction == "above":
            is_match = (num_val > threshold)
        elif direction == "equal":
            is_match = (abs(num_val - threshold) < 1e-4)
        else:  # below
            is_match = (num_val < threshold)

        return {
            "value": round(num_val, 2),
            "text": text,
            "active": bool(is_match),
            "mode": mode,
            "sampled": 1,
            "words": ocr_res.get("words", []),
        }

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
        px_access = img.load()
        # Calculate 2D stride to keep total sampled points <= _MAX_SAMPLES (4000)
        total_px = w * h
        if total_px <= _MAX_SAMPLES:
            step_x = 1
            step_y = 1
        else:
            scale = math.sqrt(total_px / float(_MAX_SAMPLES))
            step_x = max(1, int(math.ceil(scale)))
            step_y = max(1, int(math.ceil(scale)))

        if mode == "color_percentage":
            target = _hex_to_rgb(d.get("color"))
            tol = d.get("tolerance", 40)
            count = 0
            sampled = 0
            for y in range(0, h, step_y):
                for x in range(0, w, step_x):
                    p = px_access[x, y]
                    sampled += 1
                    if _rgb_dist(p, target) <= tol:
                        count += 1
            value = count / sampled * 100.0 if sampled else 0.0
        else:  # average_brightness
            total_luma = 0.0
            sampled = 0
            for y in range(0, h, step_y):
                for x in range(0, w, step_x):
                    p = px_access[x, y]
                    sampled += 1
                    total_luma += _luma(p)
            value = total_luma / sampled if sampled else 0.0

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
        self._start_root = None
        self._start_canvas = None
        self._rect_id = None

        self._win = tk.Toplevel(root)
        self._win.overrideredirect(True)
        self._win.attributes("-topmost", True)
        self._win.configure(bg="black")
        self._win.attributes("-alpha", 0.3)

        x, y, w, h = virtual_screen_bounds()
        self._win.geometry(f"{w}x{h}{x:+d}{y:+d}")
        self._win.lift()

        self._canvas = tk.Canvas(
            self._win, bg="black", highlightthickness=0, cursor="crosshair")
        self._canvas.pack(fill="both", expand=True)

        self._canvas.bind("<ButtonPress-1>", self._on_press)
        self._canvas.bind("<B1-Motion>", self._on_drag)
        self._canvas.bind("<ButtonRelease-1>", self._on_release)
        self._canvas.bind("<Escape>", self._on_escape)
        self._win.bind("<Escape>", self._on_escape)

        # Apply WS_EX_NOACTIVATE (0x08000000) so window never steals keyboard/foreground focus from games
        try:
            self._win.update_idletasks()
            hwnd = int(self._win.winfo_id())
            user32 = ctypes.windll.user32
            WS_EX_NOACTIVATE = 0x08000000
            WS_EX_LAYERED = 0x00080000
            GWL_EXSTYLE = -20
            ex = user32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            user32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_NOACTIVATE | WS_EX_LAYERED)
        except Exception:
            pass

    def show(self):
        self._win.deiconify()
        self._win.attributes("-topmost", True)
        self._win.lift()

    def close(self, result):
        try:
            self._win.destroy()
        except Exception:
            pass
        self._on_done(result)

    def _on_press(self, event):
        self._start_root = (event.x_root, event.y_root)
        self._start_canvas = (event.x, event.y)
        self._rect_id = self._canvas.create_rectangle(
            event.x, event.y, event.x, event.y,
            outline="#48B2E9", width=2, fill="", dash=(6, 3))

    def _on_drag(self, event):
        if self._start_canvas is None or self._rect_id is None:
            return
        self._canvas.coords(
            self._rect_id, self._start_canvas[0], self._start_canvas[1], event.x, event.y)

    def _on_release(self, event):
        if self._start_root is None:
            return
        x0, y0 = self._start_root
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
            holder["sel"] = sel
            sel.show()
        except Exception:
            log.warning("failed to open region selector", exc_info=True)
            done.set()

    try:
        root.after(0, _open)
    except Exception:
        return None

    if not done.wait(timeout):
        sel = holder.get("sel")
        if sel:
            try:
                root.after(0, lambda: sel.close(None))
            except Exception:
                pass
        return None
    return holder.get("rect")
