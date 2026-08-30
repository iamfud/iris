"""Iris — Centralized path resolution for installed and portable execution."""

import logging
import os
import sys

log = logging.getLogger("iris.paths")

_CACHED_PORTABLE = None
_CACHED_DOCUMENTS = None


def is_portable() -> bool:
    """Return True if Iris is running in portable mode."""
    global _CACHED_PORTABLE
    if _CACHED_PORTABLE is not None:
        return _CACHED_PORTABLE

    root = get_root_dir()
    # Check for portable indicator files in root directory
    if os.path.isfile(os.path.join(root, "portable.dat")) or os.path.isfile(os.path.join(root, ".portable")):
        _CACHED_PORTABLE = True
        return True

    # When frozen, also check next to sys.executable
    if getattr(sys, "frozen", False):
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        if os.path.isfile(os.path.join(exe_dir, "portable.dat")) or os.path.isfile(os.path.join(exe_dir, ".portable")):
            _CACHED_PORTABLE = True
            return True

    _CACHED_PORTABLE = False
    return False


def get_app_dir() -> str:
    """Return directory containing the Python source files or PyInstaller unpacked dir."""
    return os.path.dirname(os.path.abspath(__file__))


def get_root_dir() -> str:
    """Return the application root directory (where exe resides when frozen, or repo root)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    # Source execution: parent of 'app'
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _get_documents_dir_uncached() -> str:
    """Query the actual Documents folder path via Shell API (no cache)."""
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [
                    ('Data1', ctypes.c_ulong),
                    ('Data2', ctypes.c_ushort),
                    ('Data3', ctypes.c_ushort),
                    ('Data4', ctypes.c_ubyte * 8)
                ]

            SHGetKnownFolderPath = ctypes.windll.shell32.SHGetKnownFolderPath
            SHGetKnownFolderPath.argtypes = [
                ctypes.POINTER(GUID),
                wintypes.DWORD,
                wintypes.HANDLE,
                ctypes.POINTER(ctypes.c_wchar_p)
            ]

            # FOLDERID_Documents = {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            guid = GUID(0xFDD39AD0, 0x238F, 0x46AF, (0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            path_ptr = ctypes.c_wchar_p()
            hr = SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(path_ptr))
            if hr == 0:
                path = path_ptr.value
                ctypes.windll.ole32.CoTaskMemFree(path_ptr)
                return path
        except Exception:
            pass

    # Fallback: standard location
    return os.path.join(os.path.expanduser("~"), "Documents")


def get_documents_dir() -> str:
    """Return the actual Documents folder path, handling custom locations via Shell API.
    
    Caches the result but validates it still exists on each call.
    """
    global _CACHED_DOCUMENTS
    if _CACHED_DOCUMENTS is not None:
        # Validate cached path still exists and is accessible
        try:
            if os.path.isdir(_CACHED_DOCUMENTS) and os.access(_CACHED_DOCUMENTS, os.R_OK):
                return _CACHED_DOCUMENTS
        except Exception:
            pass
        # Cached path invalid - clear and re-query
        _CACHED_DOCUMENTS = None
    
    _CACHED_DOCUMENTS = _get_documents_dir_uncached()
    return _CACHED_DOCUMENTS


def invalidate_documents_cache():
    """Clear the cached Documents folder path. Call when user may have changed their Documents location."""
    global _CACHED_DOCUMENTS
    _CACHED_DOCUMENTS = None


def _migrate_iris_user_dir(old_base: str, new_base: str) -> bool:
    """Move Iris user directories from old_base to new_base.
    
    Returns True if migration was attempted, False if nothing to migrate or failed.
    """
    import shutil
    
    subdirs = ["Library", "Plugins", "Screenshots"]
    migrated_any = False
    
    for subdir in subdirs:
        old_path = os.path.join(old_base, subdir)
        new_path = os.path.join(new_base, subdir)
        
        if not os.path.isdir(old_path):
            continue
            
        if os.path.exists(new_path):
            # Target exists - merge contents
            try:
                for item in os.listdir(old_path):
                    src = os.path.join(old_path, item)
                    dst = os.path.join(new_path, item)
                    if os.path.exists(dst):
                        # Skip if destination exists (newer files win)
                        continue
                    shutil.move(src, dst)
                # Remove old directory if empty
                try:
                    os.rmdir(old_path)
                except OSError:
                    pass  # Not empty, leave it
                migrated_any = True
            except Exception as e:
                log.warning(f"[paths] Failed to merge {subdir}: {e}")
        else:
            # Target doesn't exist - move entire directory
            try:
                os.makedirs(os.path.dirname(new_path), exist_ok=True)
                shutil.move(old_path, new_path)
                migrated_any = True
            except Exception as e:
                log.warning(f"[paths] Failed to move {subdir}: {e}")
    
    # Also migrate config if it exists in old location (for portable->installed)
    old_config = os.path.join(old_base, "iris_config.json")
    new_config = os.path.join(new_base, "iris_config.json")
    if os.path.isfile(old_config) and not os.path.isfile(new_config):
        try:
            shutil.move(old_config, new_config)
            migrated_any = True
        except Exception as e:
            log.warning(f"[paths] Failed to migrate config: {e}")
    
    return migrated_any


def get_documents_dir() -> str:
    """Return the actual Documents folder path, handling custom locations via Shell API.
    
    Caches the result but validates it still exists on each call.
    """
    global _CACHED_DOCUMENTS
    if _CACHED_DOCUMENTS is not None:
        # Validate cached path still exists and is accessible
        try:
            if os.path.isdir(_CACHED_DOCUMENTS) and os.access(_CACHED_DOCUMENTS, os.R_OK):
                return _CACHED_DOCUMENTS
        except Exception:
            pass
        # Cached path invalid - clear and re-query
        _CACHED_DOCUMENTS = None
    
    new_path = _get_documents_dir_uncached()
    
    # Check if path changed (migration needed)
    if _CACHED_DOCUMENTS is not None and new_path != _CACHED_DOCUMENTS:
        log.info(f"[paths] Documents folder changed: {_CACHED_DOCUMENTS} -> {new_path}")
        old_iris_base = os.path.join(_CACHED_DOCUMENTS, "Iris")
        new_iris_base = os.path.join(new_path, "Iris")
        if _migrate_iris_user_dir(old_iris_base, new_iris_base):
            log.info("[paths] Iris user directory migrated successfully")
        else:
            log.info("[paths] No migration needed or migration failed")
    
    _CACHED_DOCUMENTS = new_path
    return _CACHED_DOCUMENTS


def invalidate_documents_cache():
    """Clear the cached Documents folder path. Call when user may have changed their Documents location."""
    global _CACHED_DOCUMENTS
    _CACHED_DOCUMENTS = None


def get_iris_user_dir() -> str:
    """Return the Iris user directory (Documents/Iris), creating it if needed."""
    base = os.path.join(get_documents_dir(), "Iris")
    os.makedirs(base, exist_ok=True)
    return base


def get_config_path() -> str:
    """Return the path to iris_config.json."""
    if is_portable():
        return os.path.join(get_root_dir(), "iris_config.json")
    if getattr(sys, "frozen", False):
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Iris")
        os.makedirs(base, exist_ok=True)
        return os.path.join(base, "iris_config.json")
    # Development mode from source: look in app/
    return os.path.join(get_app_dir(), "iris_config.json")


def get_log_dir() -> str:
    """Return directory where iris.log should be stored."""
    if is_portable():
        base = os.path.join(get_root_dir(), "logs")
        os.makedirs(base, exist_ok=True)
        return base
    if getattr(sys, "frozen", False):
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), "Iris")
        os.makedirs(base, exist_ok=True)
        return base
    return get_app_dir()


def get_log_file() -> str:
    """Return full path to iris.log."""
    return os.path.join(get_log_dir(), "iris.log")


def plugins_root() -> str:
    """Return the folder that CONTAINS the importable 'plugins' package.

    Built-in and user plugins share one visible folder:
      portable  -> <root>/plugins         (beside Iris.exe)
      installed -> Documents/Iris/plugins
    The parent is returned so callers can place it on sys.path to make
    `import plugins.<name>.connector` resolve.
    """
    if is_portable():
        return get_root_dir()
    return get_iris_user_dir()


def get_user_plugins_dir() -> str:
    """Return the single plugins directory (built-in + user add-ons), creating it if needed."""
    base = os.path.join(plugins_root(), "plugins")
    os.makedirs(base, exist_ok=True)
    return base


def get_builtin_plugins_dir() -> str:
    """Return directory of built-in plugins.

    Frozen builds ship built-ins in the same visible plugins folder as user
    add-ons (Option A: one folder).  Source runs use the bundled app/plugins.
    """
    if getattr(sys, "frozen", False):
        return get_user_plugins_dir()
    return os.path.join(get_app_dir(), "plugins")


def get_screenshots_dir(cfg: dict = None) -> str:
    """Return directory for saving and loading screenshots."""
    if cfg:
        custom = (cfg.get("screenshot_dir") or "").strip()
        if custom:
            os.makedirs(custom, exist_ok=True)
            return os.path.abspath(custom)
    if is_portable():
        base = os.path.join(get_root_dir(), "Library", "screenshots")
    else:
        base = os.path.join(get_iris_user_dir(), "Library", "screenshots")
    os.makedirs(base, exist_ok=True)
    return os.path.abspath(base)


def get_notes_dir(cfg: dict = None) -> str:
    """Return directory for saving and loading notes."""
    if cfg:
        custom = (cfg.get("notes_dir") or cfg.get("screenshot_dir") or "").strip()
        if custom:
            os.makedirs(custom, exist_ok=True)
            return os.path.abspath(custom)
    if is_portable():
        base = os.path.join(get_root_dir(), "Library", "notes")
    else:
        base = os.path.join(get_iris_user_dir(), "Library", "notes")
    os.makedirs(base, exist_ok=True)
    return os.path.abspath(base)


def get_webview_data_dir(subfolder: str = "WebView2") -> str:
    """Return user data directory for WebView2 runtime instances."""
    if is_portable():
        base = os.path.join(get_root_dir(), "data", subfolder)
    else:
        appdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~"))
        base = os.path.join(appdata, "Iris", subfolder)
    os.makedirs(base, exist_ok=True)
    return base


def get_asset_dir() -> str:
    """Return a writable, persistent dir for runtime-downloaded assets
    (e.g. the MDI font/meta fallback). In source runs the bundled app dir
    already holds these; in frozen builds we use a writable user dir because
    the _MEIPASS extract is temp and non-persistent."""
    if getattr(sys, "frozen", False):
        base = os.path.join(get_root_dir(), "data", "assets")
        os.makedirs(base, exist_ok=True)
        return base
    return get_app_dir()
