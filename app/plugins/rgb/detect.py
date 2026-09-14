"""Hardware detection routines for RGB & LCD displays (NZXT Kraken, Ajazz, etc.).

Self-contained USB PnP scanning with thread safety and TTL caching to prevent
polling overhead. Completely isolated from Iris Core.
"""

import logging
import re
import subprocess
import threading
import time
from typing import Dict, Any, Optional

log = logging.getLogger("iris.plugins.rgb.detect")

# NZXT Kraken LCD USB PIDs (VID 1E71) -> (model family, native resolution, shape).
KRAKEN_MODELS = {
    # Z53 / Z63 / Z73  -- 2.36" circular edge-to-edge LCD
    "3008": ("Kraken Z", 320, "circle"),
    # Kraken 2023 non-Elite -- 1.54" square LCD
    "300e": ("Kraken (2023)", 240, "square"),
    # Kraken 2023+ Elite -- 2.17" circular LCD
    "300c": ("Kraken 2023 Elite", 640, "circle"),
    # Kraken 2024 (may also surface as 300e/300c variants)
    "3012": ("Kraken RX (2024)", 640, "circle"),
    "3014": ("Kraken (2024)", 240, "square"),
}

_KRAKEN_CACHE: Dict[str, Any] = {"at": 0.0, "res": None}
_KRAKEN_LOCK = threading.Lock()


def probe_kraken_usb(ttl: float = 5.0) -> Dict[str, Any]:
    """Detect an attached NZXT Kraken LCD via USB PnP enumeration.

    Runs a short-lived PowerShell Get-PnpDevice query for VID_1E71 (NZXT),
    maps the PID to a known model/resolution/shape, and caches the result
    for `ttl` seconds so periodic polls do not hammer PowerShell.
    """
    now = time.time()
    with _KRAKEN_LOCK:
        if _KRAKEN_CACHE["res"] is not None and now - _KRAKEN_CACHE["at"] < ttl:
            return _KRAKEN_CACHE["res"]

        try:
            ps = (
                "Get-PnpDevice -PresentOnly -ErrorAction SilentlyContinue | "
                "Where-Object { $_.InstanceId -match 'VID_1E71' } | "
                "ForEach-Object { $_.InstanceId }"
            )
            out = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
                capture_output=True,
                text=True,
                timeout=6,
                creationflags=0x08000000,  # CREATE_NO_WINDOW
            )
            pids = set()
            for line in (out.stdout or "").splitlines():
                m = re.search(r"VID_1E71&PID_([0-9A-Fa-f]{4})", line)
                if m:
                    pids.add(m.group(1).lower())

            pick = next(iter(pids), None)
            if not pick:
                record = {"found": False}
            else:
                name, res, shape = KRAKEN_MODELS.get(pick, ("NZXT Kraken", 640, "circle"))
                record = {
                    "found": True,
                    "pid": pick,
                    "model": name,
                    "resolution": res,
                    "shape": shape,
                }
            _KRAKEN_CACHE["res"] = record
            _KRAKEN_CACHE["at"] = now
            return record
        except Exception as e:
            log.warning("[rgb.detect] Kraken USB probe failed: %s", e)
            record = {"found": False}
            _KRAKEN_CACHE["res"] = record
            _KRAKEN_CACHE["at"] = now
            return record
