"""Iris Keybinder — Minimal Single-Key Architecture (No Modifiers)

Clean, deterministic hardware scancode injection for single keys.
Designed for 100% reliability, zero ghost key bleed, and failsafe execution.
"""

from __future__ import annotations

import ctypes
import os
import time
import logging
from typing import Tuple, Optional

log = logging.getLogger("keybinder")

# ── Interception Driver C Definitions ─────────────────────────────────────

INTERCEPTION_KEY_DOWN = 0x00
INTERCEPTION_KEY_UP   = 0x01
INTERCEPTION_KEY_E0   = 0x02

class InterceptionKeyStroke(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("state", ctypes.c_ushort),
        ("information", ctypes.c_ulong),
    ]

# ── DirectInput SendInput Definitions ─────────────────────────────────────

KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP       = 0x0002
KEYEVENTF_SCANCODE    = 0x0008
INPUT_KEYBOARD        = 1

class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
    ]

class _INPUT_UNION(ctypes.Union):
    _fields_ = [("ki", _KEYBDINPUT)]

class _INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("ii", _INPUT_UNION),
    ]

# ── Direct Hardware Scancode Lookup (IBM PS/2 Set 1) ───────────────────────
# Explicit mapping from key token string to (hardware_scancode, is_extended)

KEY_SCANCODE_MAP = {
    # Digits (Main keyboard row)
    "1": (0x02, False),
    "2": (0x03, False),
    "3": (0x04, False),
    "4": (0x05, False),
    "5": (0x06, False),
    "6": (0x07, False),
    "7": (0x08, False),
    "8": (0x09, False),
    "9": (0x0A, False),
    "0": (0x0B, False),

    # Letters A-Z
    "a": (0x1E, False), "b": (0x30, False), "c": (0x2E, False),
    "d": (0x20, False), "e": (0x12, False), "f": (0x21, False),
    "g": (0x22, False), "h": (0x23, False), "i": (0x17, False),
    "j": (0x24, False), "k": (0x25, False), "l": (0x26, False),
    "m": (0x32, False), "n": (0x31, False), "o": (0x18, False),
    "p": (0x19, False), "q": (0x10, False), "r": (0x13, False),
    "s": (0x1F, False), "t": (0x14, False), "u": (0x16, False),
    "v": (0x2F, False), "w": (0x11, False), "x": (0x2D, False),
    "y": (0x15, False), "z": (0x2C, False),

    # Standard Function Keys F1 - F12
    "f1": (0x3B, False), "f2": (0x3C, False), "f3": (0x3D, False),
    "f4": (0x3E, False), "f5": (0x3F, False), "f6": (0x40, False),
    "f7": (0x41, False), "f8": (0x42, False), "f9": (0x43, False),
    "f10": (0x44, False), "f11": (0x57, False), "f12": (0x58, False),

    # Extended Function Keys F13 - F24
    "f13": (0x64, False), "f14": (0x65, False), "f15": (0x66, False),
    "f16": (0x67, False), "f17": (0x68, False), "f18": (0x69, False),
    "f19": (0x6A, False), "f20": (0x6B, False), "f21": (0x6C, False),
    "f22": (0x6D, False), "f23": (0x6E, False), "f24": (0x76, False),

    # Navigation & Action Keys
    "space": (0x39, False),
    "enter": (0x1C, False),
    "return": (0x1C, False),
    "tab": (0x0F, False),
    "backspace": (0x0E, False),
    "delete": (0x53, True),
    "insert": (0x52, True),
    "home": (0x47, True),
    "end": (0x4F, True),
    "pageup": (0x49, True),
    "pagedown": (0x51, True),
    "up": (0x48, True),
    "down": (0x50, True),
    "left": (0x4B, True),
    "right": (0x4D, True),

    # Escape (ONLY when explicitly requested)
    "esc": (0x01, False),
    "escape": (0x01, False),
}


def resolve_key(key_input: str) -> Optional[Tuple[int, bool]]:
    """Resolve user key string to (hardware_scancode, is_extended)."""
    if not isinstance(key_input, str):
        key_input = str(key_input)
    token = key_input.strip().lower()
    return KEY_SCANCODE_MAP.get(token, None)


from device_scanner import scan_devices, find_best_primary_keyboard, DeviceInfo


class SingleKeyEngine:
    """Minimal, deterministic key injection engine with device targeting."""

    def __init__(self):
        self._interception_dll = None
        self._context = None
        self.target_device = 1
        self.detected_devices: List[DeviceInfo] = []
        self.driver_status = "uninitialized"
        self._init_interception()
        self._auto_select_device()

    @staticmethod
    def _find_interception_dll() -> Optional[str]:
        candidates = [
            "interception.dll",
            r"D:\Interception\library\x64\interception.dll",
            r"D:\key\interception.dll",
            os.path.join(os.path.dirname(__file__), "interception.dll"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def _init_interception(self):
        dll_path = self._find_interception_dll()
        if not dll_path:
            self.driver_status = "dll_not_found"
            log.info("[keybinder] interception.dll not found; DirectInput fallback available")
            return

        try:
            self._interception_dll = ctypes.CDLL(dll_path)
            self._interception_dll.interception_create_context.restype = ctypes.c_void_p
            self._interception_dll.interception_send.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint
            ]
            self._interception_dll.interception_send.restype = ctypes.c_int

            ctx = self._interception_dll.interception_create_context()
            if ctx:
                self._context = ctx
                self.driver_status = "active"
                log.info("[keybinder] Interception kernel driver ACTIVE on %s", dll_path)
            else:
                self.driver_status = "context_failed"
        except Exception as ex:
            self.driver_status = f"error: {ex}"

    def _auto_select_device(self):
        """Scan all 10 slots and auto-select the best desktop keyboard candidate."""
        if self._context and self._interception_dll:
            self.detected_devices = scan_devices(self._interception_dll, self._context)
            best_slot = find_best_primary_keyboard(self.detected_devices)
            if best_slot:
                self.target_device = best_slot
                log.info("[keybinder] Auto-selected keyboard device Slot %d", self.target_device)

    def set_target_device(self, slot: int):
        """Manually set target keyboard slot (1..10)."""
        if 1 <= slot <= 10:
            self.target_device = slot
            log.info("[keybinder] Target keyboard device manually set to Slot %d", slot)

    def is_interception_active(self) -> bool:
        return self._context is not None

    def _send_interception(self, scancode: int, press: bool, is_extended: bool, device_override: Optional[int] = None):
        """Send stroke via Interception kernel driver to target device slot."""
        stroke = InterceptionKeyStroke()
        stroke.code = scancode
        state = INTERCEPTION_KEY_DOWN if press else INTERCEPTION_KEY_UP
        if is_extended:
            state |= INTERCEPTION_KEY_E0
        stroke.state = state
        stroke.information = 0
        target = device_override if device_override is not None else self.target_device
        self._interception_dll.interception_send(self._context, target, ctypes.byref(stroke), 1)

    def _send_directinput(self, scancode: int, press: bool, is_extended: bool, device_override: Optional[int] = None):
        """Send stroke via Windows DirectInput SendInput."""
        flags = KEYEVENTF_SCANCODE
        if not press:
            flags |= KEYEVENTF_KEYUP
        if is_extended:
            flags |= KEYEVENTF_EXTENDEDKEY

        extra = ctypes.c_ulong(0)
        ki = _KEYBDINPUT(0, scancode, flags, 0, ctypes.pointer(extra))
        ii = _INPUT_UNION(ki=ki)
        inp = _INPUT(INPUT_KEYBOARD, ii)
        ctypes.windll.user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))

    def tap_key(self, key_name: str, use_directinput: bool = False, device: Optional[int] = None, hold_duration: float = 0.040) -> bool:
        """Execute a single key tap with guaranteed finally release.

        Step 1: Resolve key_name to hardware scancode.
        Step 2: Send Key DOWN to target device.
        Step 3: Hold for 40ms (game frame sampling window).
        Step 4 (finally): Send Key UP for ONLY this key.
        """
        mapping = resolve_key(key_name)
        if not mapping:
            log.error("[keybinder] Unknown key name: '%s'", key_name)
            return False

        scancode, is_extended = mapping
        use_interception = self.is_interception_active() and not use_directinput

        # Dispatcher function for this tap
        send_fn = self._send_interception if use_interception else self._send_directinput

        is_down = False
        try:
            # 1. Key DOWN
            send_fn(scancode, press=True, is_extended=is_extended, device_override=device)
            is_down = True

            # 2. Hold duration (40ms = ~2.5 game frames at 60fps)
            time.sleep(hold_duration)
            return True
        except Exception as ex:
            log.error("[keybinder] tap_key error on '%s': %s", key_name, ex)
            return False
        finally:
            # 3. GUARANTEED RELEASE — ONLY for this specific key
            if is_down:
                try:
                    send_fn(scancode, press=False, is_extended=is_extended, device_override=device)
                except Exception as ex:
                    log.error("[keybinder] Key UP failed for scancode 0x%02X: %s", scancode, ex)


# Global singleton instance
key_engine = SingleKeyEngine()

