"""Iris 3.0 — Advanced Hardware Keyboard Service

Provides low-latency, gaming-grade keystroke injection with:
1. Interception Kernel Driver support (ring-0 hardware injection for DirectInput/RawInput games).
2. PnP Device Auto-Detection: Automatically targets the clean desktop keyboard, bypassing reWASD/Tartarus remaps.
3. DirectInput SendInput fallback.
4. Failsafe execution: Strict scoped try...finally release on every stroke (zero key-down lockups).
5. Rich key/combo parser (e.g. '1', '2', 'Space', 'F13', 'Ctrl+1', 'Alt+Shift+K').
"""

from __future__ import annotations

import ctypes
import os
import re
import sys
import time
import logging
from typing import List, Dict, Tuple, Optional, Union

from device_scanner import scan_devices, find_best_primary_keyboard, DeviceInfo

log = logging.getLogger("keyboard_service")

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
KEYEVENTF_UNICODE     = 0x0004
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

# ── Hardware Scancode Lookup (IBM PS/2 Set 1) ──────────────────────────────
# Maps friendly name to (hardware_scancode, is_extended, is_modifier)

KEY_MAP = {
    # Modifiers
    "ctrl": (0x1D, False, True), "control": (0x1D, False, True), "lctrl": (0x1D, False, True),
    "rctrl": (0x1D, True, True),
    "shift": (0x2A, False, True), "lshift": (0x2A, False, True), "rshift": (0x36, False, True),
    "alt": (0x38, False, True), "menu": (0x38, False, True), "lalt": (0x38, False, True),
    "ralt": (0x38, True, True),
    "win": (0x5B, True, True), "windows": (0x5B, True, True), "lwin": (0x5B, True, True), "rwin": (0x5C, True, True),

    # Digits (Main keyboard row)
    "1": (0x02, False, False), "2": (0x03, False, False), "3": (0x04, False, False),
    "4": (0x05, False, False), "5": (0x06, False, False), "6": (0x07, False, False),
    "7": (0x08, False, False), "8": (0x09, False, False), "9": (0x0A, False, False),
    "0": (0x0B, False, False),

    # Letters A-Z
    "a": (0x1E, False, False), "b": (0x30, False, False), "c": (0x2E, False, False),
    "d": (0x20, False, False), "e": (0x12, False, False), "f": (0x21, False, False),
    "g": (0x22, False, False), "h": (0x23, False, False), "i": (0x17, False, False),
    "j": (0x24, False, False), "k": (0x25, False, False), "l": (0x26, False, False),
    "m": (0x32, False, False), "n": (0x31, False, False), "o": (0x18, False, False),
    "p": (0x19, False, False), "q": (0x10, False, False), "r": (0x13, False, False),
    "s": (0x1F, False, False), "t": (0x14, False, False), "u": (0x16, False, False),
    "v": (0x2F, False, False), "w": (0x11, False, False), "x": (0x2D, False, False),
    "y": (0x15, False, False), "z": (0x2C, False, False),

    # Function Keys F1 - F12
    "f1": (0x3B, False, False), "f2": (0x3C, False, False), "f3": (0x3D, False, False),
    "f4": (0x3E, False, False), "f5": (0x3F, False, False), "f6": (0x40, False, False),
    "f7": (0x41, False, False), "f8": (0x42, False, False), "f9": (0x43, False, False),
    "f10": (0x44, False, False), "f11": (0x57, False, False), "f12": (0x58, False, False),

    # Extended Function Keys F13 - F24
    "f13": (0x64, False, False), "f14": (0x65, False, False), "f15": (0x66, False, False),
    "f16": (0x67, False, False), "f17": (0x68, False, False), "f18": (0x69, False, False),
    "f19": (0x6A, False, False), "f20": (0x6B, False, False), "f21": (0x6C, False, False),
    "f22": (0x6D, False, False), "f23": (0x6E, False, False), "f24": (0x76, False, False),

    # Navigation & Action Keys
    "space": (0x39, False, False), "spacebar": (0x39, False, False),
    "enter": (0x1C, False, False), "return": (0x1C, False, False),
    "tab": (0x0F, False, False),
    "backspace": (0x0E, False, False), "bksp": (0x0E, False, False),
    "delete": (0x53, True, False), "del": (0x53, True, False),
    "insert": (0x52, True, False), "ins": (0x52, True, False),
    "home": (0x47, True, False), "end": (0x4F, True, False),
    "pageup": (0x49, True, False), "pgup": (0x49, True, False),
    "pagedown": (0x51, True, False), "pgdn": (0x51, True, False),
    "up": (0x48, True, False), "down": (0x50, True, False),
    "left": (0x4B, True, False), "right": (0x4D, True, False),
    "capslock": (0x3A, False, False), "numlock": (0x45, False, False), "scrolllock": (0x46, False, False),

    # Symbols & Punctuation
    "-": (0x0C, False, False), "=": (0x0D, False, False), "[": (0x1A, False, False),
    "]": (0x1B, False, False), ";": (0x27, False, False), "'": (0x28, False, False),
    "`": (0x29, False, False), "\\": (0x2B, False, False), ",": (0x33, False, False),
    ".": (0x34, False, False), "/": (0x35, False, False),

    # Numpad (NumLock ON — same scan codes as navigation, non-extended)
    "numpad0": (0x52, False, False), "num0": (0x52, False, False),
    "numpad1": (0x4F, False, False), "num1": (0x4F, False, False),
    "numpad2": (0x50, False, False), "num2": (0x50, False, False),
    "numpad3": (0x51, False, False), "num3": (0x51, False, False),
    "numpad4": (0x4B, False, False), "num4": (0x4B, False, False),
    "numpad5": (0x4C, False, False), "num5": (0x4C, False, False),
    "numpad6": (0x4D, False, False), "num6": (0x4D, False, False),
    "numpad7": (0x47, False, False), "num7": (0x47, False, False),
    "numpad8": (0x48, False, False), "num8": (0x48, False, False),
    "numpad9": (0x49, False, False), "num9": (0x49, False, False),
    "numpadenter": (0x1C, True, False), "numenter": (0x1C, True, False),
    "numpadadd": (0x4E, False, False), "num+": (0x4E, False, False), "numadd": (0x4E, False, False),
    "numpadminus": (0x4A, False, False), "num-": (0x4A, False, False), "numsubtract": (0x4A, False, False),
    "numpadmultiply": (0x37, False, False), "num*": (0x37, False, False), "nummult": (0x37, False, False),
    "numpaddivide": (0x35, True, False), "num/": (0x35, True, False), "numdiv": (0x35, True, False),
    "numpaddecimal": (0x53, False, False), "num.": (0x53, False, False), "numdec": (0x53, False, False),

    # Escape (ONLY when explicitly asked)
    "esc": (0x01, False, False), "escape": (0x01, False, False),
}

# Legacy Virtual Key code fallback table
VK_MAP = {
    0x10: (0x2A, False), 0x11: (0x1D, False), 0x12: (0x38, False),
    0x08: (0x0E, False), 0x09: (0x0F, False), 0x0D: (0x1C, False), 0x1B: (0x01, False),
    0x20: (0x39, False), 0x30: (0x0B, False), 0x31: (0x02, False), 0x32: (0x03, False),
    0x33: (0x04, False), 0x34: (0x05, False), 0x35: (0x06, False), 0x36: (0x07, False),
    0x37: (0x08, False), 0x38: (0x09, False), 0x39: (0x0A, False),
}

# US QWERTY character → (scancode, is_extended, requires_shift).
# Derived from KEY_MAP so literal text can be typed through the same hardware
# scancode path as key taps (works in games where SendInput unicode is blocked).
CHAR_MAP = {
    _k: (_v[0], _v[1], False)
    for _k, _v in KEY_MAP.items()
    if len(_k) == 1 and not _v[2]
}
# Uppercase letters = Shift + lowercase
for _ch in "abcdefghijklmnopqrstuvwxyz":
    CHAR_MAP[_ch.upper()] = (CHAR_MAP[_ch][0], CHAR_MAP[_ch][1], True)
# Shifted symbols
for _shifted, _base in {
    "~": "`", "!": "1", "@": "2", "#": "3", "$": "4", "%": "5",
    "^": "6", "&": "7", "*": "8", "(": "9", ")": "0",
    "_": "-", "+": "=", "{": "[", "}": "]", ":": ";",
    '"': "'", "|": "\\", "<": ",", ">": ".", "?": "/",
}.items():
    if _base in CHAR_MAP:
        CHAR_MAP[_shifted] = (CHAR_MAP[_base][0], CHAR_MAP[_base][1], True)
CHAR_MAP[" "] = (KEY_MAP["space"][0], False, False)


def parse_hotkey(query: Union[str, List, int]) -> List[Tuple[int, bool, bool]]:
    """Parse hotkey string ('ctrl+1', 'space', 'f13') or legacy list into (scancode, is_extended, is_modifier)."""
    if isinstance(query, int):
        # Legacy VK integer (e.g. 49 for '1')
        if 1 <= query <= 9:
            token = str(query)
            if token in KEY_MAP:
                return [KEY_MAP[token]]
        elif query in VK_MAP:
            sc, ext = VK_MAP[query]
            return [(sc, ext, False)]
        return []

    if isinstance(query, list):
        out = []
        for item in query:
            out.extend(parse_hotkey(item))
        return out

    if not isinstance(query, str):
        return []

    parts = query.lower().replace(",", "+").split("+")
    parsed = []
    for p in parts:
        token = p.strip()
        if not token:
            continue
        if token in KEY_MAP:
            parsed.append(KEY_MAP[token])
        else:
            log.warning("[keyboard_service] Unknown key token: '%s'", token)
    return parsed


# Sequence grammar: whitespace separates key combos and quoted text segments.
# 'enter "Hello World" enter' → [tap enter, type "Hello World", tap enter].
_SEQUENCE_TOKEN_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\S+')


def parse_sequence(query: str) -> List[Dict]:
    """Parse a hotkey sequence string into ordered actions.

    Bare tokens are key combos (parse_hotkey: 'ctrl+1', 'space', 'enter', ...).
    Quoted segments are literal text to type.
    Escapes inside quotes: \\" → " and \\\\ → \\.
    """
    if not isinstance(query, str):
        return []
    actions = []
    for m in _SEQUENCE_TOKEN_RE.finditer(query):
        tok = m.group(0)
        if tok.startswith('"'):
            text = tok[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            actions.append({"type": "text", "text": text})
        else:
            if parse_hotkey(tok):
                actions.append({"type": "keys", "token": tok})
    return actions


class KeyboardService:
    """Core hardware keyboard injection service with device routing."""

    def __init__(self):
        self._interception_dll = None
        self._context = None
        self.target_device: int = 1
        self.detected_devices: List[DeviceInfo] = []
        self.driver_status: str = "uninitialized"
        self._init_interception()
        self._auto_select_device()

    @staticmethod
    def _find_interception_dll() -> Optional[str]:
        candidates = [
            "interception.dll",
            r"D:\Interception\library\x64\interception.dll",
            r"D:\key\interception.dll",
            os.path.join(os.path.dirname(__file__), "interception.dll"),
            os.path.join(os.path.dirname(__file__), "..", "Keybinder", "interception.dll"),
        ]
        for c in candidates:
            if os.path.exists(c):
                return c
        return None

    def _init_interception(self):
        dll_path = self._find_interception_dll()
        if not dll_path:
            self.driver_status = "dll_not_found"
            log.info("[keyboard_service] interception.dll not found; using DirectInput SendInput fallback")
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
                log.info("[keyboard_service] Interception driver ACTIVE context created via %s", dll_path)
            else:
                self.driver_status = "context_failed"
                log.warning("[keyboard_service] Interception context creation failed")
        except Exception as ex:
            self.driver_status = f"error: {ex}"
            log.warning("[keyboard_service] Interception DLL load failed: %s", ex)

    def _auto_select_device(self):
        """Scan all slots and auto-select primary desktop keyboard."""
        if self._context and self._interception_dll:
            self.detected_devices = scan_devices(self._interception_dll, self._context)
            best_slot = find_best_primary_keyboard(self.detected_devices)
            if best_slot:
                self.target_device = best_slot
                log.info("[keyboard_service] Auto-routed keyboard target to Slot %d", self.target_device)

    def set_target_device(self, slot: int):
        """Set target keyboard device slot (1..10)."""
        if 1 <= slot <= 10:
            self.target_device = slot
            log.info("[keyboard_service] Target keyboard device slot set to %d", slot)

    def is_interception_active(self) -> bool:
        return self._context is not None

    def get_devices(self) -> List[dict]:
        """Return list of detected devices for UI display."""
        if self._context and self._interception_dll:
            self.detected_devices = scan_devices(self._interception_dll, self._context)
        return [d.to_dict() for d in self.detected_devices]

    def _send_interception(self, scancode: int, press: bool, is_extended: bool, device: Optional[int] = None):
        stroke = InterceptionKeyStroke()
        stroke.code = scancode
        state = INTERCEPTION_KEY_DOWN if press else INTERCEPTION_KEY_UP
        if is_extended:
            state |= INTERCEPTION_KEY_E0
        stroke.state = state
        stroke.information = 0
        target = device if device is not None else self.target_device
        self._interception_dll.interception_send(self._context, target, ctypes.byref(stroke), 1)

    def _send_directinput(self, scancode: int, press: bool, is_extended: bool, device: Optional[int] = None):
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

    def tap_key(self, key_name: str, device: Optional[int] = None, hold_duration: float = 0.040) -> bool:
        """Execute a single key tap with guaranteed finally release."""
        return self.send_hotkey(key_name, device=device, hold_duration=hold_duration)

    def send_hotkey(self, keys: Union[str, List, int], device: Optional[int] = None, hold_duration: float = 0.045) -> bool:
        """Send a single key or modifier combo with guaranteed scoped release.

        Pipeline:
        1. Modifiers DOWN in forward order (e.g. Ctrl, Alt).
        2. Primary Key DOWN (e.g. '1', 'F13', 'Space').
        3. Hold for hold_duration (45ms).
        4. finally: Unconditionally release in reverse order ONLY for pressed keys.
        """
        strokes = parse_hotkey(keys)
        if not strokes:
            return False

        use_interception = self.is_interception_active()
        send_fn = self._send_interception if use_interception else self._send_directinput

        # Separate modifiers from primary key
        modifiers = [s for s in strokes if s[2]]
        primary_keys = [s for s in strokes if not s[2]]

        # Check if any primary key is a numpad digit / decimal that requires NumLock
        numpad_scancodes = {0x52, 0x4F, 0x50, 0x51, 0x4B, 0x4C, 0x4D, 0x47, 0x48, 0x49, 0x53}
        needs_numlock = any(sc in numpad_scancodes and not ext for sc, ext, _ in primary_keys)
        toggled_numlock = False

        if needs_numlock:
            try:
                # VK_NUMLOCK = 0x90. Low-order bit indicates toggle state (1 = ON, 0 = OFF)
                numlock_state = ctypes.windll.user32.GetKeyState(0x90) & 1
                if not numlock_state:
                    # Temporarily turn NumLock ON so game receives true numpad number
                    send_fn(0x45, press=True, is_extended=False, device=device)
                    send_fn(0x45, press=False, is_extended=False, device=device)
                    toggled_numlock = True
                    time.sleep(0.010)
            except Exception:
                pass

        # Order to press: modifiers first, then primary keys
        press_sequence = modifiers + primary_keys
        pressed_scancodes = []

        try:
            # 1. Press down in order
            for sc, ext, is_mod in press_sequence:
                send_fn(sc, press=True, is_extended=ext, device=device)
                pressed_scancodes.append((sc, ext))
                if len(press_sequence) > 1:
                    time.sleep(0.010)

            # 2. Hold key combination for game engine polling (45ms)
            time.sleep(hold_duration)
            return True
        except Exception as ex:
            log.error("[keyboard_service] send_hotkey error: %s", ex)
            return False
        finally:
            # 3. GUARANTEED UNCONDITIONAL RELEASE — only for keys that were actively pressed!
            for sc, ext in reversed(pressed_scancodes):
                try:
                    send_fn(sc, press=False, is_extended=ext, device=device)
                except Exception as ex:
                    log.error("[keyboard_service] key release failed for scancode 0x%02X: %s", sc, ex)
                if len(pressed_scancodes) > 1:
                    time.sleep(0.005)

            if toggled_numlock:
                try:
                    # Restore previous NumLock state
                    send_fn(0x45, press=True, is_extended=False, device=device)
                    send_fn(0x45, press=False, is_extended=False, device=device)
                except Exception:
                    pass

    def _send_unicode_char(self, char: str, device: Optional[int] = None):
        """Send one character via SendInput KEYEVENTF_UNICODE (goes to the focused window).

        Unicode injection can't go through the Interception scancode driver, so this
        always uses SendInput — the correct path for typing literal text into the
        active application (chat boxes, search bars, etc.).
        """
        extra = ctypes.c_ulong(0)
        for up in (0, KEYEVENTF_KEYUP):
            ki = _KEYBDINPUT(0, ord(char), KEYEVENTF_UNICODE | up, 0, ctypes.pointer(extra))
            ii = _INPUT_UNION(ki=ki)
            inp = _INPUT(INPUT_KEYBOARD, ii)
            ctypes.windll.user32.SendInput(1, ctypes.pointer(inp), ctypes.sizeof(inp))
            time.sleep(0.004)

    def type_text(self, text: str, device: Optional[int] = None, char_delay: float = 0.030) -> bool:
        """Type literal text character-by-character into the focused window.

        Uses the same hardware scancode path as key taps (with Shift handled
        per character) so it works wherever a tapped key works — including
        DirectInput games that reject SendInput unicode. Characters not on the
        US scancode layout fall back to SendInput KEYEVENTF_UNICODE.
        """
        if not text:
            return True
        use_interception = self.is_interception_active()
        send_fn = self._send_interception if use_interception else self._send_directinput
        for ch in text:
            entry = CHAR_MAP.get(ch)
            try:
                if entry is None:
                    self._send_unicode_char(ch, device=device)
                else:
                    sc, ext, shifted = entry
                    if shifted:
                        send_fn(0x2A, press=True, is_extended=False, device=device)
                    send_fn(sc, press=True, is_extended=ext, device=device)
                    time.sleep(0.012)
                    send_fn(sc, press=False, is_extended=ext, device=device)
                    if shifted:
                        send_fn(0x2A, press=False, is_extended=False, device=device)
            except Exception as ex:
                log.error("[keyboard_service] type_text error on %r: %s", ch, ex)
                return False
            time.sleep(char_delay)
        return True

    def send_sequence(self, keys: Union[str, List, int], device: Optional[int] = None,
                      hold_duration: float = 0.045, char_delay: float = 0.030) -> bool:
        """Send a hotkey sequence, e.g. 'enter "Hello World" enter'.

        Bare tokens are key combos, quoted segments are typed literally.
        Falls back to send_hotkey for plain combos / legacy inputs.
        """
        if not isinstance(keys, str) or isinstance(keys, (list, int)):
            return self.send_hotkey(keys, device=device, hold_duration=hold_duration)
        actions = parse_sequence(keys)
        if not actions:
            return False
        if len(actions) == 1 and actions[0]["type"] == "keys":
            return self.send_hotkey(actions[0]["token"], device=device, hold_duration=hold_duration)
        for act in actions:
            if act["type"] == "text":
                self.type_text(act["text"], device=device, char_delay=char_delay)
            else:
                self.send_hotkey(act["token"], device=device, hold_duration=hold_duration)
            time.sleep(0.020)
        return True


# Global singleton instance for Iris 3.0
keyboard_service = KeyboardService()
