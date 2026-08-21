"""Hardware PnP Device Scanner for Interception Keyboard Slots (1..10).

Discovers, identifies, and classifies all connected keyboard devices
using their USB Vendor ID (VID) and Product ID (PID).
"""

from __future__ import annotations

import ctypes
import os
from typing import List, Dict, Optional, Tuple

# Known USB Vendor IDs (VID)
KNOWN_VENDORS = {
    "1532": "Razer",
    "046D": "Logitech",
    "1B1C": "Corsair",
    "1038": "SteelSeries",
    "045E": "Microsoft",
    "0955": "NVIDIA",
    "0B05": "ASUS",
    "17EF": "Lenovo",
    "413C": "Dell",
    "04F2": "Chicony",
    "3434": "Keychron",
    "04D9": "Holtek",
    "05AC": "Apple",
    "258A": "Sinowealth",
}

# Known macro pads / keypads to flag
MACRO_PAD_KEYWORDS = ["tartarus", "orbweaver", "nostromo", "azeron", "streamdeck", "keypad"]

# Virtual driver keywords to flag
VIRTUAL_KEYWORDS = ["rewasd", "virtual", "vjoy", "vigem", "root\\", "parsec"]


class DeviceInfo:
    def __init__(self, slot: int, hardware_id: str):
        self.slot = slot
        self.hardware_id = hardware_id
        self.vendor_id = ""
        self.product_id = ""
        self.vendor_name = "Unknown Vendor"
        self.device_type = "UNKNOWN"
        self.description = ""
        self._parse()

    def _parse(self):
        hw = self.hardware_id.upper()
        if not hw:
            self.device_type = "EMPTY"
            self.description = "No device attached"
            return

        # Extract VID and PID
        if "VID_" in hw:
            idx = hw.find("VID_") + 4
            self.vendor_id = hw[idx:idx + 4]
            self.vendor_name = KNOWN_VENDORS.get(self.vendor_id, f"Vendor 0x{self.vendor_id}")

        if "PID_" in hw:
            idx = hw.find("PID_") + 4
            self.product_id = hw[idx:idx + 4]

        hw_lower = self.hardware_id.lower()

        # Check for virtual drivers
        if any(vk in hw_lower for vk in VIRTUAL_KEYWORDS):
            self.device_type = "VIRTUAL_DRIVER"
            self.description = f"Virtual Device ({self.vendor_name})"
            return

        # Check for macro pads (e.g. Razer Tartarus)
        if any(mk in hw_lower for mk in MACRO_PAD_KEYWORDS) or (self.vendor_id == "1532" and self.product_id in ["022B", "0208", "011B", "0234"]):
            self.device_type = "MACRO_PAD"
            self.description = f"Gaming Keypad ({self.vendor_name} Tartarus / Macro Pad)"
            return

        # Check for Mouse keyboard endpoint (macro keys on gaming mouse)
        if "MI_01" in hw or "MI_02" in hw or "mouse" in hw_lower:
            self.device_type = "MOUSE_ENDPOINT"
            self.description = f"Mouse Keyboard Endpoint ({self.vendor_name})"
            return

        # Standard / ACPI keyboard
        if "ACPI" in hw or "PNP0303" in hw:
            self.device_type = "PRIMARY_KEYBOARD"
            self.description = "Standard PS/2 / Motherboard Keyboard"
            return

        # Standard USB Keyboard
        if "HID" in hw or "USB" in hw:
            self.device_type = "PRIMARY_KEYBOARD"
            self.description = f"Physical USB Keyboard ({self.vendor_name})"
            return

        self.device_type = "KEYBOARD"
        self.description = f"Keyboard Device ({self.vendor_name})"


def scan_devices(interception_dll, context) -> List[DeviceInfo]:
    """Scan all 10 keyboard slots and return a list of DeviceInfo."""
    if not interception_dll or not context:
        return []

    interception_dll.interception_get_hardware_id.argtypes = [
        ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint
    ]
    interception_dll.interception_get_hardware_id.restype = ctypes.c_uint

    devices = []
    for slot in range(1, 11):
        buf = ctypes.create_unicode_buffer(512)
        length = interception_dll.interception_get_hardware_id(
            context, slot, ctypes.byref(buf), ctypes.sizeof(buf)
        )
        hwid = buf.value if length > 0 else ""
        dev = DeviceInfo(slot, hwid)
        if dev.device_type != "EMPTY":
            devices.append(dev)

    return devices


def find_best_primary_keyboard(devices: List[DeviceInfo]) -> Optional[int]:
    """Find the best candidate slot for the primary desktop keyboard."""
    # Priority 1: Physical USB keyboard that is NOT a macro pad, NOT virtual, NOT a mouse
    for d in devices:
        if d.device_type == "PRIMARY_KEYBOARD" and d.vendor_id and d.vendor_id != "1532":  # Non-Razer USB keyboard
            return d.slot

    # Priority 2: Any primary keyboard (including Razer desktop keyboards that are not Tartarus)
    for d in devices:
        if d.device_type == "PRIMARY_KEYBOARD":
            return d.slot

    # Priority 3: First non-macro, non-virtual keyboard
    for d in devices:
        if d.device_type not in ["MACRO_PAD", "VIRTUAL_DRIVER", "MOUSE_ENDPOINT", "EMPTY"]:
            return d.slot

    # Fallback to slot 1 if devices exist
    return devices[0].slot if devices else 1
