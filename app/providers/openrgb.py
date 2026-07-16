import glob
import logging
import os
import threading

import pystray

log = logging.getLogger("iris.openrgb")


def _openrgb_profiles_dir():
    for base in (os.environ.get("APPDATA", ""), os.environ.get("LOCALAPPDATA", "")):
        d = os.path.join(base, "OpenRGB", "profiles")
        if os.path.isdir(d):
            return d
        d = os.path.join(base, "OpenRGB")
        if os.path.isdir(d):
            return d
    return None


def _list_profile_files():
    d = _openrgb_profiles_dir()
    if not d:
        return []
    files = glob.glob(os.path.join(d, "*.orp"))
    return sorted(files)


def _profile_name_from_path(path):
    return os.path.splitext(os.path.basename(path))[0]


def _apply_profile(path, name):
    try:
        from openrgb import OpenRGBClient
        from openrgb.utils import LocalProfile
    except ImportError:
        log.warning("[openrgb] openrgb-python not installed")
        return
    try:
        with open(path, "rb") as f:
            profile = LocalProfile.unpack(f)
    except Exception as e:
        log.warning(f"[openrgb] failed to parse {name!r}: {e}")
        return
    profile_controllers = list(profile.controllers)
    try:
        client = OpenRGBClient()
    except ConnectionRefusedError:
        log.warning("[openrgb] SDK server not running — enable it in OpenRGB Settings")
        return
    except Exception as e:
        log.warning(f"[openrgb] SDK connect failed: {e}")
        return
    applied = 0
    used = set()
    for device in client.devices:
        match = None
        for i, ctrl in enumerate(profile_controllers):
            if i in used:
                continue
            if ctrl.name == device.name:
                match = ctrl
                used.add(i)
                break
        if match is None:
            log.debug(f"[openrgb] no profile entry for {device.name!r}")
            continue
        try:
            profile_mode_name = match.modes[match.active_mode].name
            live_mode = next(
                (m for m in device.modes if m.name == profile_mode_name), None
            )
            if live_mode is not None:
                device.set_mode(live_mode)
            if match.colors:
                colors = match.colors
                live_count = len(device.leds)
                if len(colors) != live_count:
                    colors = (colors * (live_count // len(colors) + 1))[:live_count]
                device.set_colors(colors)
            applied += 1
        except Exception as e:
            log.warning(f"[openrgb] {device.name!r}: {e}")
    log.info(f"[openrgb] {name!r}: applied to {applied}/{len(client.devices)} device(s)")


class OpenRGBProvider:
    def __init__(self, cfg):
        self.cfg = cfg
        self._running = False
        self._profiles = []
        self._profile_lock = threading.Lock()
        self._last_scan = 0.0

    def start(self):
        if not self.cfg.get("openrgb_enabled", False):
            log.info("[openrgb] disabled via config")
            return
        self._running = True

    def stop(self):
        self._running = False

    def _scan_profiles(self):
        import time
        now = time.time()
        if now - self._last_scan < 10.0:
            return
        self._last_scan = now
        files = _list_profile_files()
        with self._profile_lock:
            self._profiles = files

    def _load_profile(self, path, *args):
        name = _profile_name_from_path(path)
        threading.Thread(target=self._apply_profile, args=(path, name), daemon=True).start()

    def _apply_profile(self, path, name):
        _apply_profile(path, name)

    def menu_items(self):
        self._scan_profiles()
        items = []
        items.append(pystray.MenuItem("OpenRGB", None, enabled=False))
        with self._profile_lock:
            profiles = list(self._profiles)
        if profiles:
            for path in profiles:
                name = _profile_name_from_path(path)
                items.append(pystray.MenuItem(
                    name, lambda *a, p=path: self._load_profile(p)))
        return items
