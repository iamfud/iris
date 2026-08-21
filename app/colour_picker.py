"""Iris — Core screen colour picker.

Launched from a panel button (entity ``system.colour_picker``). Grabbing
needs no fullscreen overlay window — it is driven entirely by a Windows
low-level mouse hook.

Threading model (the reason there is no mouse jitter and no re-entrant Tk
crash):

* a **dedicated hook thread** installs ``WH_MOUSE_LL``/``WH_KEYBOARD_LL``
  and pumps its own Windows message queue. Its callbacks only do cheap
  native work — ``SetCursor`` (round-grid picker over the display, normal
  arrow over the Iris panel) and enqueueing pixel-grab requests. It never
  touches Tk.
* a **worker thread** performs the (relatively slow) ``ImageGrab`` pixel
  reads, throttled, and marshals results back to the Tk thread via
  ``root.after`` — so the mainloop is never blocked and the cursor never
  jitters.
* the Tk thread only runs the re-apply timer, the picker page updates and
  the session teardown.

Nothing system-wide is mutated (no ``SetSystemCursor``), so a crashed Iris
process can never leave the cursor stuck.
"""

from __future__ import annotations

import ctypes
import logging
import os
import queue
import struct
import tempfile
import threading
import time
from io import BytesIO

from ctypes import wintypes
from PIL import Image, ImageDraw, ImageGrab

log = logging.getLogger("iris.colour_picker")

user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32

WH_MOUSE_LL = 14
WH_KEYBOARD_LL = 13

WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_KEYDOWN = 0x0100
WM_QUIT = 0x0012
VK_ESCAPE = 0x1B
IDC_ARROW = 32512

_STOP = object()  # worker-queue sentinel

_LRESULT = ctypes.c_ssize_t
_LOW_LEVEL_MOUSE_PROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
_LOW_LEVEL_KEYBD_PROC = ctypes.WINFUNCTYPE(_LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

user32.SetWindowsHookExW.restype = ctypes.c_void_p
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD]
user32.CallNextHookEx.restype = _LRESULT
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]

# Message pump (dedicated hook thread)
user32.GetMessageW.restype = ctypes.c_int
user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), ctypes.c_void_p, wintypes.UINT, wintypes.UINT]
user32.PeekMessageW.restype = ctypes.c_int
user32.PeekMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), ctypes.c_void_p, wintypes.UINT, wintypes.UINT, wintypes.UINT]
user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
user32.PostThreadMessageW.restype = wintypes.BOOL
user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
_kernel32.GetCurrentThreadId.restype = wintypes.DWORD

# Cursor APIs: restypes are mandatory on 64-bit Windows — a missing restype
# truncates the HCURSOR to 32 bits and SetCursor silently fails.
user32.LoadCursorW.restype = ctypes.c_void_p
user32.LoadCursorW.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
user32.LoadCursorFromFileW.restype = ctypes.c_void_p
user32.LoadCursorFromFileW.argtypes = [wintypes.LPCWSTR]
user32.SetCursor.restype = ctypes.c_void_p
user32.SetCursor.argtypes = [ctypes.c_void_p]

_kernel32.GetModuleHandleW.restype = ctypes.c_void_p
_kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]


class _POINT(ctypes.Structure):
    _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt", _POINT),
        ("mouseData", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("vkCode", wintypes.DWORD),
        ("scanCode", wintypes.DWORD),
        ("flags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class _RECT(ctypes.Structure):
    _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

user32.GetCursorPos.restype = wintypes.BOOL
user32.GetCursorPos.argtypes = [ctypes.POINTER(_POINT)]


def _hex_of(rgb):
    return "#%02x%02x%02x" % tuple(rgb[:3])


# ── Round-grid cursor ──────────────────────────────────────────────────
# The native Win11 eyedropper cursor cannot be reused from a Tk window,
# so a .cur is generated once with Pillow and loaded via LoadCursorFromFileW.

_CURSOR_PATH = None


def _make_round_grid_cursor(path, size=32):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c = size // 2
    r = size // 2 - 1
    # outer ring: black casing under a white rim
    d.ellipse((c - r - 1, c - r - 1, c + r + 1, c + r + 1), outline=(0, 0, 0, 255), width=3)
    d.ellipse((c - r, c - r, c + r, c + r), outline=(255, 255, 255, 255), width=2)
    # faint grid inside the ring
    for g in (-6, 6):
        d.line((c + g, c - r + 3, c + g, c + r - 3), fill=(255, 255, 255, 80), width=1)
        d.line((c - r + 3, c + g, c + r - 3, c + g), fill=(255, 255, 255, 80), width=1)
    # crosshair (black casing, white core)
    arm = r - 4
    d.line((c - arm, c, c + arm, c), fill=(0, 0, 0, 255), width=3)
    d.line((c, c - arm, c, c + arm), fill=(0, 0, 0, 255), width=3)
    d.line((c - arm, c, c + arm, c), fill=(255, 255, 255, 255), width=1)
    d.line((c, c - arm, c, c + arm), fill=(255, 255, 255, 255), width=1)
    # centre dot
    d.ellipse((c - 2, c - 2, c + 2, c + 2), fill=(0, 0, 0, 255), outline=(255, 255, 255, 255))

    buf = BytesIO()
    img.save(buf, format="PNG")
    png = buf.getvalue()
    hotspot = size // 2
    header = struct.pack("<HHH", 0, 2, 1)  # reserved, type=CUR, count=1
    entry = struct.pack("<BBBBHHII", size, size, 0, 0, hotspot, hotspot, len(png), 22)
    with open(path, "wb") as f:
        f.write(header)
        f.write(entry)
        f.write(png)


def _cursor_path():
    global _CURSOR_PATH
    if _CURSOR_PATH and os.path.exists(_CURSOR_PATH):
        return _CURSOR_PATH
    try:
        path = os.path.join(tempfile.gettempdir(), "iris_round_grid_cursor.cur")
        _make_round_grid_cursor(path)
        _CURSOR_PATH = path
    except Exception as e:
        log.warning("[colour_picker] cursor build failed: %s", e)
        _CURSOR_PATH = None
    return _CURSOR_PATH


_arrow_cursor = None
_picker_cursor = None


def _load_arrow():
    return user32.LoadCursorW(None, ctypes.c_void_p(IDC_ARROW))


def _cursors():
    """Return (arrow_hcursor, picker_hcursor)."""
    global _arrow_cursor, _picker_cursor
    if _arrow_cursor is None:
        _arrow_cursor = _load_arrow()
    if _picker_cursor is None:
        p = _cursor_path()
        if p:
            _picker_cursor = user32.LoadCursorFromFileW(p)
    return _arrow_cursor, _picker_cursor


class ColourPickSession:
    """Active screen-colour grabbing session.

    ``begin()``/``end()`` are called from the Tk thread; the hooks run on a
    dedicated thread and pixel reads on a worker thread.
    """

    def __init__(self, exclude_hwnd, root=None, on_preview=None, on_colour=None, on_cancel=None):
        self._exclude = int(exclude_hwnd)
        self._root = root
        self._on_preview = on_preview
        self._on_colour = on_colour
        self._on_cancel = on_cancel
        self._active = False
        self._lock = threading.Lock()
        self._mouse_proc = None
        self._key_proc = None
        self._mouse_hook = None
        self._key_hook = None
        self._hook_thread = None
        self._thread_id = None
        self._installed = threading.Event()
        self._worker = None
        self._queue = None
        self._arrow = None
        self._picker = None
        self._timer_id = None
        self._last_preview = 0.0

    @property
    def active(self):
        return self._active

    # ── Hook callbacks (run on the dedicated hook thread; NO Tk here) ───

    def _inside_iris(self, x, y):
        try:
            rect = _RECT()
            if user32.GetWindowRect(self._exclude, ctypes.byref(rect)):
                return rect.left <= x <= rect.right and rect.top <= y <= rect.bottom
        except Exception:
            pass
        return False

    def _cursor_pos(self):
        try:
            pt = _POINT()
            if user32.GetCursorPos(ctypes.byref(pt)):
                return pt.x, pt.y
        except Exception:
            pass
        return None

    def _mouse_cb(self, nCode, wParam, lParam):
        if nCode >= 0 and self._active:
            wm = wParam & 0xFFFF
            ms = ctypes.cast(lParam, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
            x, y = ms.pt.x, ms.pt.y
            if wm == WM_MOUSEMOVE:
                over = self._inside_iris(x, y)
                if self._picker is not None:
                    user32.SetCursor(self._arrow if over else self._picker)
                if not over:
                    self._request_preview(x, y)
            elif wm == WM_LBUTTONDOWN:
                if not self._inside_iris(x, y):
                    self._grab(x, y)
                    return 1
            elif wm == WM_RBUTTONDOWN:
                if not self._inside_iris(x, y):
                    self._cancel()
                    return 1
        return user32.CallNextHookEx(self._mouse_hook, nCode, wParam, lParam)

    def _key_cb(self, nCode, wParam, lParam):
        if nCode >= 0 and self._active and (wParam & 0xFFFF) == WM_KEYDOWN:
            kbd = ctypes.cast(lParam, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
            if kbd.vkCode == VK_ESCAPE:
                self._cancel()
                return 1
        return user32.CallNextHookEx(self._key_hook, nCode, wParam, lParam)

    # ── Grab requests (cheap enqueue from the hook thread) ──────────────

    def _request_preview(self, x, y):
        now = time.monotonic()
        if now - self._last_preview < 0.12:
            return
        self._last_preview = now
        try:
            self._queue.put_nowait(("preview", x, y))
        except Exception:
            pass

    def _grab(self, x, y):
        try:
            self._queue.put_nowait(("grab", x, y))
        except Exception:
            pass
        self._stop()

    def _cancel(self):
        self._stop()
        self._tkip(self._on_cancel)

    # ── Worker thread (the only place ImageGrab runs) ───────────────────

    def _worker_loop(self):
        while True:
            try:
                item = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            if item is _STOP:
                break
            kind, x, y = item
            try:
                img = ImageGrab.grab((x, y, x + 1, y + 1))
                rgb = tuple(img.getpixel((0, 0))[:3])
            except Exception as e:
                log.warning("[colour_picker] grab failed: %s", e)
                continue
            hexs = _hex_of(rgb)
            if kind == "grab":
                self._tkip(self._on_colour, hexs, rgb)
            else:
                self._tkip(self._on_preview, hexs, rgb)

    # ── Marshalling back to the Tk thread ───────────────────────────────

    def _tkip(self, fn, *args):
        if not fn:
            return
        if self._root is not None:
            try:
                self._root.after(0, lambda: self._safe(fn, *args))
                return
            except Exception:
                pass
        self._safe(fn, *args)

    @staticmethod
    def _safe(fn, *args):
        try:
            fn(*args)
        except Exception as e:
            log.warning("[colour_picker] callback failed: %s", e)

    # ── Cursor re-apply timer (Tk thread; fights WM_SETCURSOR resets) ───

    def _apply_cursor(self):
        if self._picker is None:
            return
        try:
            pos = self._cursor_pos()
            over = self._inside_iris(*pos) if pos else False
            user32.SetCursor(self._arrow if over else self._picker)
        except Exception:
            pass

    def _schedule_timer(self):
        if not self._root or not self._active:
            return
        self._timer_id = self._root.after(30, self._on_timer)

    def _on_timer(self):
        if not self._active:
            return
        self._apply_cursor()
        self._schedule_timer()

    # ── Lifecycle ───────────────────────────────────────────────────────

    def begin(self):
        """Start the hook thread + worker. Call from the Tk thread."""
        with self._lock:
            if self._active:
                return self
            self._active = True
        self._arrow, self._picker = _cursors()
        self._last_preview = 0.0
        self._queue = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True, name="iris-picker-grab")
        self._worker.start()
        self._hook_thread = threading.Thread(target=self._hook_loop, daemon=True, name="iris-picker-hook")
        self._hook_thread.start()
        self._installed.wait(timeout=1.0)
        if not (self._mouse_hook and self._key_hook):
            log.warning("[colour_picker] hooks not installed (mouse=%s key=%s)",
                        self._mouse_hook, self._key_hook)
            self._stop()
            return self
        self._apply_cursor()
        self._schedule_timer()
        return self

    def _hook_loop(self):
        """Install hooks and pump this thread's own message queue."""
        hmod = _kernel32.GetModuleHandleW(None)
        self._mouse_proc = _LOW_LEVEL_MOUSE_PROC(self._mouse_cb)
        self._key_proc = _LOW_LEVEL_KEYBD_PROC(self._key_cb)
        self._mouse_hook = user32.SetWindowsHookExW(WH_MOUSE_LL, self._mouse_proc, hmod, 0)
        self._key_hook = user32.SetWindowsHookExW(WH_KEYBOARD_LL, self._key_proc, hmod, 0)
        # Ensure a message queue exists so PostThreadMessageW(Win_QUIT) lands.
        msg = wintypes.MSG()
        user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, 0x0001)  # PM_NOREMOVE
        self._thread_id = _kernel32.GetCurrentThreadId()
        self._installed.set()
        try:
            while True:
                r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r <= 0:
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
        finally:
            for hook in (self._mouse_hook, self._key_hook):
                if hook:
                    try:
                        user32.UnhookWindowsHookEx(hook)
                    except Exception:
                        pass
            self._mouse_hook = self._key_hook = None
            self._thread_id = None

    def _stop(self):
        """Tear down hooks/worker. Safe from any thread."""
        with self._lock:
            if not self._active:
                return
            self._active = False
        if self._thread_id:
            try:
                user32.PostThreadMessageW(self._thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        try:
            self._queue.put_nowait(_STOP)
        except Exception:
            pass
        if self._arrow:
            try:
                user32.SetCursor(self._arrow)
            except Exception:
                pass

    def end(self):
        """Safely tear down the session. Call from the Tk thread."""
        self._stop()
        if self._timer_id is not None and self._root is not None:
            try:
                self._root.after_cancel(self._timer_id)
            except Exception:
                pass
            self._timer_id = None