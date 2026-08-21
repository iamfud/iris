"""Iris — Windows platform utilities."""

import os
import logging
import threading
from PIL import Image

log = logging.getLogger("iris.platform")
_DIALOG_LOCK = threading.Lock()




def get_current_default_audio_output():
    """Return the endpoint ID of the current default audio render device, or None."""
    try:
        import comtypes
        from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
        from pycaw.constants import CLSID_MMDeviceEnumerator, EDataFlow, ERole
        comtypes.CoInitialize()
        de = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator, IMMDeviceEnumerator,
            comtypes.CLSCTX_INPROC_SERVER)
        default = de.GetDefaultAudioEndpoint(EDataFlow.eRender.value, ERole.eConsole.value)
        return default.GetId()
    except Exception as e:
        log.debug("[audio] get_current_default: %s", e)
        return None




def set_default_audio_output(device_key: str) -> bool:
    """Set the Windows default audio playback device."""
    endpoint_id = None

    if device_key.startswith("sd:"):
        try:
            import sounddevice as sd
            import comtypes
            from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
            from pycaw.constants import CLSID_MMDeviceEnumerator, EDataFlow
            from pycaw.utils import AudioUtilities
            sd_idx = int(device_key[3:])
            target_name = sd.query_devices(sd_idx)['name']
            comtypes.CoInitialize()
            de = comtypes.CoCreateInstance(
                CLSID_MMDeviceEnumerator, IMMDeviceEnumerator,
                comtypes.CLSCTX_INPROC_SERVER)
            col = de.EnumAudioEndpoints(EDataFlow.eRender.value, 1)
            render_ids = {col.Item(i).GetId() for i in range(col.GetCount())}
            for d in AudioUtilities.GetAllDevices():
                if d.id in render_ids:
                    fn = d.FriendlyName or ""
                    if target_name in fn or fn in target_name:
                        endpoint_id = d.id
                        break
        except Exception as e:
            log.warning("[audio] resolve sd:%s -> endpoint: %s", device_key[3:], e)
    else:
        endpoint_id = device_key

    if not endpoint_id:
        log.warning("[audio] could not resolve endpoint ID for %r", device_key)
        return False

    try:
        import comtypes
        from pycaw.utils import AudioUtilities
        from pycaw.constants import ERole
        comtypes.CoInitialize()
        AudioUtilities.SetDefaultDevice(
            endpoint_id,
            roles=[ERole.eConsole, ERole.eMultimedia, ERole.eCommunications],
        )
        log.info("[audio] default output set -> %s", endpoint_id[:50])
        return True
    except ImportError:
        log.debug("[audio] pycaw not available")
        return False
    except Exception as e:
        log.warning("[audio] set_default_audio_output: %s", e)
        return False


def toggle_mic_mute() -> bool | None:
    """Toggle mute on the default capture (microphone) device.

    Returns the new mute state (True=muted, False=unmuted) on success,
    or None on failure.
    """
    try:
        import comtypes
        from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
        from pycaw.constants import CLSID_MMDeviceEnumerator, EDataFlow, ERole
        from pycaw.api.endpointvolume import IAudioEndpointVolume

        comtypes.CoInitialize()
        de = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator, IMMDeviceEnumerator,
            comtypes.CLSCTX_INPROC_SERVER)
        device = de.GetDefaultAudioEndpoint(
            EDataFlow.eCapture.value, ERole.eConsole.value)
        IID = comtypes.GUID("{5CDF2C82-841E-4546-9722-0CF74078229A}")
        epv = device.Activate(IID, comtypes.CLSCTX_INPROC_SERVER, None)
        epv = epv.QueryInterface(IAudioEndpointVolume)
        current = epv.GetMute()
        epv.SetMute(not current, None)
        return not current
    except ImportError:
        log.debug("[audio] pycaw not available for mic mute")
        return None
    except Exception as e:
        log.warning("[audio] toggle_mic_mute: %s", e)
        return None


def get_mic_mute_state() -> bool | None:
    """Return current mute state of default microphone (True=muted, False=unmuted)."""
    try:
        import comtypes
        from pycaw.api.mmdeviceapi import IMMDeviceEnumerator
        from pycaw.constants import CLSID_MMDeviceEnumerator, EDataFlow, ERole
        from pycaw.api.endpointvolume import IAudioEndpointVolume

        comtypes.CoInitialize()
        de = comtypes.CoCreateInstance(
            CLSID_MMDeviceEnumerator, IMMDeviceEnumerator,
            comtypes.CLSCTX_INPROC_SERVER)
        device = de.GetDefaultAudioEndpoint(
            EDataFlow.eCapture.value, ERole.eConsole.value)
        IID = comtypes.GUID("{5CDF2C82-841E-4546-9722-0CF74078229A}")
        epv = device.Activate(IID, comtypes.CLSCTX_INPROC_SERVER, None)
        epv = epv.QueryInterface(IAudioEndpointVolume)
        return bool(epv.GetMute())
    except Exception:
        return None


# ── UWP / MSIX Store-app resolution ──────────────────────────────
_APPX_RESOLVE_CACHE: dict = {}  # normcase(abs) → real exe path or None


def _resolve_appx_exe(icon_path: str) -> str | None:
    """Resolve a 0-byte WindowsApps AppExecutionAlias stub to the real MSIX package exe.

    Returns the real exe path or None. Results are cached so the 1-s panel
    poll never re-spawns PowerShell for the same stub.
    """
    import os, subprocess, base64

    norm = os.path.normcase(os.path.abspath(icon_path))
    if norm in _APPX_RESOLVE_CACHE:
        return _APPX_RESOLVE_CACHE[norm]

    try:
        # Only resolve 0-byte .exe stubs (AppExecutionAliases)
        if not icon_path.lower().endswith(".exe") or os.path.getsize(icon_path) > 0:
            _APPX_RESOLVE_CACHE[norm] = None
            return None

        leaf = os.path.basename(icon_path)

        # Pass the exe name via env var to avoid PS injection (same pattern as
        # IRIS_ICON_PATH / IRIS_ICON_OUT used elsewhere in _extract_via_ps).
        env = os.environ.copy()
        env["IRIS_APPX_LEAF"] = leaf

        # Query every installed package to find one containing this exe.
        ps = (
            "$leaf = $env:IRIS_APPX_LEAF; "
            "$pkg = Get-AppxPackage | Where-Object { "
            "  Test-Path (Join-Path $_.InstallLocation $leaf)"
            "} | Select-Object -First 1; "
            "if ($pkg) { Write-Output (Join-Path $pkg.InstallLocation $leaf) }"
        )

        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            env=env, capture_output=True, text=True, timeout=15,
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )

        resolved = (result.stdout or "").strip().strip('"\'')
        if resolved and os.path.isfile(resolved):
            _APPX_RESOLVE_CACHE[norm] = resolved
            return resolved

        _APPX_RESOLVE_CACHE[norm] = None
        return None

    except Exception:
        _APPX_RESOLVE_CACHE[norm] = None
        return None


def _extract_via_ps(icon_path, size=256):
    """Extract an app icon via native Windows Shell API (256x256 Jumbo High-DPI) or fallback.
    
    Returns a PIL RGBA Image or None.
    """
    import os
    import subprocess
    import tempfile
    from PIL import Image

    if not icon_path:
        return None

    icon_path = str(icon_path).strip().strip('"\'')
    icon_path = os.path.expandvars(os.path.expanduser(icon_path))
    if not os.path.isfile(icon_path):
        import shutil
        which_p = shutil.which(icon_path)
        if which_p and os.path.isfile(which_p):
            icon_path = which_p
        else:
            import shlex
            try:
                parts = shlex.split(icon_path, posix=False)
                if parts:
                    first_token = parts[0].strip('"\'')
                    first_token = os.path.expandvars(os.path.expanduser(first_token))
                    which_first = shutil.which(first_token) or (first_token if os.path.isfile(first_token) else None)
                    if which_first and os.path.isfile(which_first):
                        icon_path = which_first
            except Exception:
                pass
        if not os.path.isfile(icon_path):
            return None

    # Resolve .lnk shortcuts if possible
    if icon_path.lower().endswith(".lnk"):
        try:
            import win32com.client  # type: ignore
            shell = win32com.client.Dispatch("WScript.Shell")
            sc = shell.CreateShortCut(icon_path)
            if sc.TargetPath and os.path.isfile(sc.TargetPath):
                icon_path = sc.TargetPath
        except Exception:
            pass

    # Resolve Windows Store (UWP/MSIX) AppExecutionAlias stubs
    _store_resolved = _resolve_appx_exe(icon_path)
    if _store_resolved:
        icon_path = _store_resolved

    # Direct image formats (PNG, ICO, JPG, BMP, WEBP)
    ext = os.path.splitext(icon_path)[1].lower()
    if ext in (".png", ".ico", ".jpg", ".jpeg", ".bmp", ".webp"):
        try:
            img = Image.open(icon_path)
            if ext == ".ico":
                best_frame = 0
                best_size = 0
                try:
                    for i in range(getattr(img, "n_frames", 1)):
                        img.seek(i)
                        s = img.size[0] * img.size[1]
                        if s > best_size:
                            best_size = s
                            best_frame = i
                    img.seek(best_frame)
                except Exception:
                    pass
            img.load()
            return _normalize_icon_size(img.convert("RGBA"), size)
        except Exception:
            pass

    # Helper: Convert Windows HICON to PIL RGBA Image via GDI+ DIBits
    def _hicon_to_image(hicon, target_size=size):
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        gdi32.GetObjectW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        gdi32.GetObjectW.restype = ctypes.c_int
        gdi32.GetDIBits.argtypes = [ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT, wintypes.UINT, ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
        gdi32.GetDIBits.restype = ctypes.c_int
        gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
        gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
        user32.ReleaseDC.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
        user32.DestroyIcon.argtypes = [ctypes.c_void_p]
        user32.GetIconInfo.argtypes = [ctypes.c_void_p, ctypes.c_void_p]

        class _ICONINFO(ctypes.Structure):
            _fields_ = [
                ("fIcon", wintypes.BOOL),
                ("xHotspot", wintypes.DWORD),
                ("yHotspot", wintypes.DWORD),
                ("hbmMask", ctypes.c_void_p),
                ("hbmColor", ctypes.c_void_p),
            ]
        info = _ICONINFO()
        if not user32.GetIconInfo(hicon, ctypes.byref(info)):
            user32.DestroyIcon(hicon)
            return None

        class _BITMAP(ctypes.Structure):
            _fields_ = [
                ("bmType", wintypes.LONG),
                ("bmWidth", wintypes.LONG),
                ("bmHeight", wintypes.LONG),
                ("bmWidthBytes", wintypes.LONG),
                ("bmPlanes", wintypes.WORD),
                ("bmBitsPixel", wintypes.WORD),
                ("bmBits", ctypes.c_void_p),
            ]
        bm = _BITMAP()
        gdi32.GetObjectW(info.hbmColor, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, bm.bmHeight
        if w <= 0 or h <= 0:
            w, h = target_size, target_size

        hdc_screen = user32.GetDC(0)
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)

        class _BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", wintypes.DWORD),
                ("biWidth", wintypes.LONG),
                ("biHeight", wintypes.LONG),
                ("biPlanes", wintypes.WORD),
                ("biBitCount", wintypes.WORD),
                ("biCompression", wintypes.DWORD),
                ("biSizeImage", wintypes.DWORD),
                ("biXPelsPerMeter", wintypes.LONG),
                ("biYPelsPerMeter", wintypes.LONG),
                ("biClrUsed", wintypes.DWORD),
                ("biClrImportant", wintypes.DWORD),
            ]
        bmi = _BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
        bmi.biWidth = w
        bmi.biHeight = -h
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buf = ctypes.create_string_buffer(w * h * 4)
        gdi32.GetDIBits(hdc_mem, info.hbmColor, 0, h, buf, ctypes.byref(bmi), 0)

        gdi32.DeleteDC(hdc_mem)
        user32.ReleaseDC(0, hdc_screen)
        if info.hbmColor: gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask: gdi32.DeleteObject(info.hbmMask)
        user32.DestroyIcon(hicon)

        raw = bytes(buf)
        img = Image.frombuffer("RGBA", (w, h), raw, "raw", "BGRA", 0, 1)
        return img

    # 1. Primary: Windows Shell SHGetImageList (SHIL_JUMBO = 256x256, SHIL_EXTRALARGE = 48x48)
    try:
        import ctypes
        from ctypes import wintypes
        shell32 = ctypes.windll.shell32
        comctl32 = ctypes.windll.comctl32
        ole32 = ctypes.windll.ole32

        ole32.CoInitialize(None)
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", wintypes.BYTE * 8)
            ]
        IID_IImageList = GUID(0x46eb5926, 0x582e, 0x4017, (wintypes.BYTE * 8)(0x9f, 0xdf, 0xe8, 0x99, 0x8d, 0xaa, 0x09, 0x50))

        class SHFILEINFOW(ctypes.Structure):
            _fields_ = [
                ("hIcon", ctypes.c_void_p),
                ("iIcon", ctypes.c_int),
                ("dwAttributes", wintypes.DWORD),
                ("szDisplayName", wintypes.WCHAR * 260),
                ("szTypeName", wintypes.WCHAR * 80)
            ]
        sfi = SHFILEINFOW()
        if shell32.SHGetFileInfoW(icon_path, 0, ctypes.byref(sfi), ctypes.sizeof(sfi), 0x4000): # SHGFI_SYSICONINDEX = 0x4000
            for shil in (4, 2, 0): # SHIL_JUMBO (256x256), SHIL_EXTRALARGE (48x48), SHIL_LARGE (32x32)
                himl = ctypes.c_void_p()
                if shell32.SHGetImageList(shil, ctypes.byref(IID_IImageList), ctypes.byref(himl)) == 0 and himl:
                    hicon = comctl32.ImageList_GetIcon(himl, sfi.iIcon, 1) # ILD_TRANSPARENT = 1
                    if hicon:
                        img = _hicon_to_image(hicon, size)
                        if img:
                            return _normalize_icon_size(img, size)
    except Exception as ex:
        log.debug("[extract] Shell image list extraction failed: %s", ex)

    # 2. Secondary: Native Win32 PrivateExtractIconsW
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        hicon = ctypes.c_void_p()
        icon_id = wintypes.UINT()
        ret = user32.PrivateExtractIconsW(icon_path, 0, size, size, ctypes.byref(hicon), ctypes.byref(icon_id), 1, 0)
        if ret > 0 and hicon:
            img = _hicon_to_image(hicon, size)
            if img:
                return _normalize_icon_size(img, size)
    except Exception as ex:
        log.debug("[extract] PrivateExtractIconsW failed: %s", ex)

    # 3. Fallback: PowerShell ExtractAssociatedIcon
    try:
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)

        env = os.environ.copy()
        env["IRIS_ICON_PATH"] = icon_path
        env["IRIS_ICON_OUT"] = tmp

        ps = (
            'Add-Type -AssemblyName System.Drawing; '
            '$p = $env:IRIS_ICON_PATH; '
            '$o = $env:IRIS_ICON_OUT; '
            'try { '
            '  if ($p.ToLower().EndsWith(".lnk")) { '
            '    $sh = New-Object -ComObject WScript.Shell; '
            '    $sc = $sh.CreateShortcut($p); '
            '    if ($sc.TargetPath -and (Test-Path $sc.TargetPath)) { $p = $sc.TargetPath; } '
            '  } '
            '  $icon = [System.Drawing.Icon]::ExtractAssociatedIcon($p); '
            '  if ($icon) { $icon.ToBitmap().Save($o, [System.Drawing.Imaging.ImageFormat]::Png); } '
            '} catch { exit 1 }'
        )

        subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps],
            env=env, capture_output=True, timeout=15,
            creationflags=0x08000000,
        )

        if os.path.isfile(tmp) and os.path.getsize(tmp) > 0:
            img = Image.open(tmp)
            img.load()
            os.unlink(tmp)
            return _normalize_icon_size(img.convert("RGBA"), size)

        os.unlink(tmp)
    except Exception as e:
        log.debug("[extract] PS icon extraction failed: %s", e)
        try:
            os.unlink(tmp)
        except Exception:
            pass
    return None


def _normalize_icon_size(img, target_size=256):
    """Ensure icon content fills the canvas cleanly without oversized transparent margins."""
    if not img:
        return None
    try:
        from PIL import Image
        bbox = img.getbbox()
        if not bbox:
            return img
        bw = bbox[2] - bbox[0]
        bh = bbox[3] - bbox[1]
        w, h = img.size
        # If the icon content is much smaller than the canvas (e.g. 32x32 or 48x48 placed inside 256x256)
        if (bw < w * 0.75 and bh < h * 0.75) or (w < target_size or h < target_size):
            cropped = img.crop(bbox)
            max_dim = max(bw, bh)
            if max_dim <= 0:
                return img
            scale = float(target_size) / float(max_dim)
            nw = max(1, int(round(bw * scale)))
            nh = max(1, int(round(bh * scale)))
            resample_filter = getattr(Image, "Resampling", Image).LANCZOS
            resized = cropped.resize((nw, nh), resample_filter)
            final_img = Image.new("RGBA", (target_size, target_size), (0, 0, 0, 0))
            ox = (target_size - nw) // 2
            oy = (target_size - nh) // 2
            final_img.paste(resized, (ox, oy))
            return final_img
    except Exception as ex:
        log.debug("[normalize_icon] error: %s", ex)
    return img


def detect_icon_color(img: Image.Image) -> str:
    """Analyze image edges and interior to return a matching #RRGGBB hex color."""
    if not img:
        return ""
    try:
        img_rgba = img.convert("RGBA")
        w, h = img_rgba.size
        if w == 0 or h == 0:
            return ""
        pixels = img_rgba.load()

        # 1. Sample perimeter pixels (top, bottom, left, right edges)
        edge_rgbs = []
        for x in range(w):
            for y in (0, h - 1):
                r, g, b, a = pixels[x, y]
                if a > 120:
                    edge_rgbs.append((r, g, b))
        for y in range(1, h - 1):
            for x in (0, w - 1):
                r, g, b, a = pixels[x, y]
                if a > 120:
                    edge_rgbs.append((r, g, b))

        # If edges have significant non-transparent pixels, compute average edge color
        if len(edge_rgbs) >= 8:
            avg_r = sum(c[0] for c in edge_rgbs) // len(edge_rgbs)
            avg_g = sum(c[1] for c in edge_rgbs) // len(edge_rgbs)
            avg_b = sum(c[2] for c in edge_rgbs) // len(edge_rgbs)
            return f"#{avg_r:02x}{avg_g:02x}{avg_b:02x}"

        # 2. If edges are transparent, find dominant vibrant color in interior
        small = img_rgba.resize((48, 48), Image.Resampling.BOX) if (w > 48 or h > 48) else img_rgba
        colors = small.getcolors(maxcolors=48 * 48)
        if colors:
            best_color = None
            best_score = -1
            for count, (r, g, b, a) in colors:
                if a < 80:
                    continue
                max_c, min_c = max(r, g, b), min(r, g, b)
                sat = (max_c - min_c) / 255.0
                lum = (max_c + min_c) / 510.0
                # Filter out pure black / very dark and pure white / very pale
                if lum < 0.08 or lum > 0.95:
                    continue
                # Score combines pixel count with saturation weighting
                score = count * (sat * 2.0 + 0.5)
                if score > best_score:
                    best_score = score
                    best_color = (r, g, b)
            if best_color:
                return f"#{best_color[0]:02x}{best_color[1]:02x}{best_color[2]:02x}"
    except Exception as e:
        log.debug("[detect_icon_color] error: %s", e)
    return ""


def open_file_dialog(title="Choose File", file_filter="Icons & Executables (*.ico;*.exe;*.png;*.lnk;*.dll)|*.ico;*.exe;*.png;*.lnk;*.dll|All files (*.*)|*.*", root=None) -> str:
    """Safely open a native Windows OpenFileDialog using Tk main thread or dedicated STA worker."""
    if not _DIALOG_LOCK.acquire(blocking=False):
        # A file dialog is already active on screen, ignore concurrent requests
        return ""
    try:
        is_exe = ("Executable" in str(title)) or ("exe" in str(file_filter).lower())
        if is_exe:
            ftypes = [
                ("Executables & Shortcuts", "*.exe *.lnk *.bat *.cmd"),
                ("Executable Files (*.exe)", "*.exe"),
                ("Shortcuts (*.lnk)", "*.lnk"),
                ("All files (*.*)", "*.*"),
            ]
        else:
            ftypes = [
                ("Icons & Executables", "*.ico *.exe *.png *.lnk *.dll"),
                ("Icon Files (*.ico)", "*.ico"),
                ("PNG Images (*.png)", "*.png"),
                ("Executable Files (*.exe)", "*.exe"),
                ("All files (*.*)", "*.*"),
            ]

        # 1. Marshal to Tk root main thread if available
        if root is not None:
            done = threading.Event()
            result = [""]

            def _open_tk():
                try:
                    import tkinter.filedialog as fd
                    path = fd.askopenfilename(parent=root, title=title, filetypes=ftypes)
                    result[0] = path or ""
                except Exception as ex:
                    log.debug("[dialog] Tk filedialog failed: %s", ex)
                finally:
                    done.set()

            root.after(0, _open_tk)
            done.wait(timeout=180)
            return result[0]

        # 2. Standalone STA Tk worker thread
        done = threading.Event()
        result = [""]

        def _worker():
            try:
                import tkinter as tk
                from tkinter import filedialog as fd
                t_root = tk.Tk()
                t_root.withdraw()
                t_root.attributes("-topmost", True)
                path = fd.askopenfilename(parent=t_root, title=title, filetypes=ftypes)
                result[0] = path or ""
                t_root.destroy()
            except Exception as ex:
                log.debug("[dialog] Standalone Tk filedialog failed: %s", ex)
            finally:
                done.set()

        th = threading.Thread(target=_worker, daemon=True)
        th.start()
        done.wait(timeout=180)
        return result[0]
    except Exception as e:
        log.warning("[dialog] open_file_dialog failed: %s", e)
    finally:
        _DIALOG_LOCK.release()
    return ""


def open_folder_dialog(title="Choose Folder", root=None) -> str:
    """Safely open a native Windows folder picker using Tk main thread or a dedicated STA worker."""
    if not _DIALOG_LOCK.acquire(blocking=False):
        # A dialog is already active on screen, ignore concurrent requests
        return ""
    try:
        # 1. Marshal to Tk root main thread if available
        if root is not None:
            done = threading.Event()
            result = [""]

            def _open_tk():
                try:
                    import tkinter.filedialog as fd
                    path = fd.askdirectory(parent=root, title=title, mustexist=False)
                    result[0] = path or ""
                except Exception as ex:
                    log.debug("[dialog] Tk folder dialog failed: %s", ex)
                finally:
                    done.set()

            root.after(0, _open_tk)
            done.wait(timeout=180)
            return result[0]

        # 2. Standalone STA Tk worker thread
        done = threading.Event()
        result = [""]

        def _worker():
            try:
                import tkinter as tk
                from tkinter import filedialog as fd
                t_root = tk.Tk()
                t_root.withdraw()
                t_root.attributes("-topmost", True)
                path = fd.askdirectory(parent=t_root, title=title, mustexist=False)
                result[0] = path or ""
                t_root.destroy()
            except Exception as ex:
                log.debug("[dialog] Standalone Tk folder dialog failed: %s", ex)
            finally:
                done.set()

        th = threading.Thread(target=_worker, daemon=True)
        th.start()
        done.wait(timeout=180)
        return result[0]
    except Exception as e:
        log.warning("[dialog] open_folder_dialog failed: %s", e)
    finally:
        _DIALOG_LOCK.release()
    return ""


def detect_installed_media_players() -> list[dict]:
    """Detect installed media players from Windows registry and standard install locations."""
    players = []
    seen_paths = set()
    seen_names = set()

    def _add(name: str, p: str):
        if not p:
            return
        norm = os.path.normpath(p)
        if norm.lower() in seen_paths or name.lower() in seen_names:
            return
        if os.path.isfile(norm):
            seen_paths.add(norm.lower())
            seen_names.add(name.lower())
            players.append({"name": name, "path": norm})

    # 1. Known executable paths (Standard and Microsoft Store / UWP)
    known = [
        ("Spotify", os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe")),
        ("Spotify", os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe")),
        ("Spotify", os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\SpotifyAB.SpotifyMusic_zpdnekdrzrea0\Spotify.exe")),
        ("iTunes", os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\iTunes.exe")),
        ("iTunes", os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\AppleInc.iTunes_nzyj5cx40ttqa\iTunes.exe")),
        ("iTunes", os.path.expandvars(r"%ProgramFiles%\iTunes\iTunes.exe")),
        ("iTunes", os.path.expandvars(r"%ProgramFiles(x86)%\iTunes\iTunes.exe")),
        ("Apple Music", os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\AppleMusic.exe")),
        ("VLC Media Player", os.path.expandvars(r"%ProgramFiles%\VideoLAN\VLC\vlc.exe")),
        ("VLC Media Player", os.path.expandvars(r"%ProgramFiles(x86)%\VideoLAN\VLC\vlc.exe")),
        ("Windows Media Player", os.path.expandvars(r"%ProgramFiles%\Windows Media Player\wmplayer.exe")),
        ("Windows Media Player", os.path.expandvars(r"%ProgramFiles(x86)%\Windows Media Player\wmplayer.exe")),
        ("foobar2000", os.path.expandvars(r"%ProgramFiles%\foobar2000\foobar2000.exe")),
        ("foobar2000", os.path.expandvars(r"%ProgramFiles(x86)%\foobar2000\foobar2000.exe")),
        ("MusicBee", os.path.expandvars(r"%ProgramFiles%\MusicBee\MusicBee.exe")),
        ("MusicBee", os.path.expandvars(r"%ProgramFiles(x86)%\MusicBee\MusicBee.exe")),
        ("MusicBee", os.path.expandvars(r"%APPDATA%\MusicBee\MusicBee.exe")),
        ("AIMP", os.path.expandvars(r"%ProgramFiles%\AIMP\AIMP.exe")),
        ("AIMP", os.path.expandvars(r"%ProgramFiles(x86)%\AIMP\AIMP.exe")),
        ("TIDAL", os.path.expandvars(r"%LOCALAPPDATA%\TIDAL\TIDAL.exe")),
        ("TIDAL", os.path.expandvars(r"%LOCALAPPDATA%\Programs\TIDAL\TIDAL.exe")),
        ("Plexamp", os.path.expandvars(r"%LOCALAPPDATA%\Programs\Plexamp\Plexamp.exe")),
        ("MPC-HC", os.path.expandvars(r"%ProgramFiles%\MPC-HC\mpc-hc64.exe")),
        ("MPC-HC", os.path.expandvars(r"%ProgramFiles(x86)%\MPC-HC\mpc-hc.exe")),
        ("MPC-BE", os.path.expandvars(r"%ProgramFiles%\MPC-BE\mpc-be64.exe")),
        ("MPC-BE", os.path.expandvars(r"%ProgramFiles(x86)%\MPC-BE\mpc-be.exe")),
        ("Winamp", os.path.expandvars(r"%ProgramFiles(x86)%\Winamp\winamp.exe")),
    ]
    for name, p in known:
        _add(name, p)

    # 1b. Scan WindowsApps execution aliases directory
    wapps_dir = os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps")
    if os.path.isdir(wapps_dir):
        try:
            for f in os.listdir(wapps_dir):
                fl = f.lower()
                if fl == "itunes.exe":
                    _add("iTunes", os.path.join(wapps_dir, f))
                elif fl == "spotify.exe":
                    _add("Spotify", os.path.join(wapps_dir, f))
                elif fl == "applemusic.exe":
                    _add("Apple Music", os.path.join(wapps_dir, f))
        except Exception:
            pass

    # 2. Windows Registry scan
    try:
        import winreg
        app_keys = [
            ("Spotify", "spotify.exe"),
            ("VLC Media Player", "vlc.exe"),
            ("Windows Media Player", "wmplayer.exe"),
            ("foobar2000", "foobar2000.exe"),
            ("MusicBee", "musicbee.exe"),
            ("AIMP", "aimp.exe"),
            ("iTunes", "itunes.exe"),
            ("TIDAL", "tidal.exe"),
            ("Plexamp", "plexamp.exe"),
            ("MPC-HC", "mpc-hc64.exe"),
            ("MPC-HC", "mpc-hc.exe"),
            ("MPC-BE", "mpc-be64.exe"),
            ("MPC-BE", "mpc-be.exe"),
            ("Winamp", "winamp.exe"),
        ]
        for root_key in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for name, exe_key in app_keys:
                try:
                    with winreg.OpenKey(root_key, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe_key}") as k:
                        val, _ = winreg.QueryValueEx(k, "")
                        if val:
                            _add(name, val.strip('"'))
                except Exception:
                    pass

            try:
                with winreg.OpenKey(root_key, r"SOFTWARE\Clients\Media") as k:
                    num_subkeys = winreg.QueryInfoKey(k)[0]
                    for i in range(num_subkeys):
                        sub = winreg.EnumKey(k, i)
                        try:
                            with winreg.OpenKey(k, rf"{sub}\shell\open\command") as cmd_k:
                                val, _ = winreg.QueryValueEx(cmd_k, "")
                                if val:
                                    exe = val.split('"')[1] if '"' in val else val.split()[0]
                                    _add(sub, exe)
                        except Exception:
                            pass
            except Exception:
                pass
    except Exception as ex:
        log.debug("[win_platform] media player registry scan error: %s", ex)

    return players


def bring_media_player_to_foreground(target_path: str = "") -> bool:
    """Bring running media player application window to the foreground.

    If the application window is found and brought to the foreground, returns True.
    If not running or no window exists, returns False so caller can launch it.
    """
    import ctypes
    import psutil

    target_name = ""
    if target_path:
        target_name = os.path.basename(target_path.strip().strip('"\'')).lower()
        if target_name.endswith(".lnk"):
            target_name = target_name[:-4].lower()

    candidate_names = set()
    if target_name:
        candidate_names.add(target_name)
        if not target_name.endswith(".exe"):
            candidate_names.add(target_name + ".exe")
        if "spotify" in target_name:
            candidate_names.add("spotify.exe")
        elif "vlc" in target_name:
            candidate_names.add("vlc.exe")
        elif "itunes" in target_name:
            candidate_names.add("itunes.exe")
        elif "musicbee" in target_name:
            candidate_names.add("musicbee.exe")
        elif "aimp" in target_name:
            candidate_names.add("aimp.exe")
    else:
        candidate_names = {
            "spotify.exe", "itunes.exe", "vlc.exe", "musicbee.exe",
            "foobar2000.exe", "aimp.exe", "tidal.exe", "plexamp.exe",
            "wmplayer.exe", "applemusic.exe", "mpc-hc64.exe", "mpc-hc.exe",
            "mpc-be64.exe", "mpc-be.exe", "winamp.exe"
        }

    target_pids = set()
    for proc in psutil.process_iter(["pid", "name"]):
        try:
            pname = (proc.info.get("name") or "").lower()
            if pname in candidate_names:
                target_pids.add(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not target_pids:
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    found_hwnds = []

    def enum_cb(hwnd, _):
        if not user32.IsWindow(hwnd):
            return True
        lp_pid = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(lp_pid))
        if lp_pid.value in target_pids:
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                found_hwnds.append(hwnd)
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p)
    cb = WNDENUMPROC(enum_cb)
    try:
        user32.EnumWindows(cb, 0)
    except Exception as ex:
        log.debug("[win_platform] EnumWindows error: %s", ex)

    if not found_hwnds:
        return False

    SW_RESTORE = 9
    SW_SHOW = 5
    HWND_TOPMOST = -1
    HWND_NOTOPMOST = -2
    SWP_NOMOVE = 0x0002
    SWP_NOSIZE = 0x0001
    SWP_SHOWWINDOW = 0x0040

    activated = False
    for hwnd in found_hwnds:
        try:
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, SW_RESTORE)
            else:
                user32.ShowWindow(hwnd, SW_SHOW)

            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
            user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)

            fg_hwnd = user32.GetForegroundWindow()
            fg_thread = user32.GetWindowThreadProcessId(fg_hwnd, None) if fg_hwnd else 0
            cur_thread = kernel32.GetCurrentThreadId()

            if fg_thread and fg_thread != cur_thread:
                user32.AttachThreadInput(cur_thread, fg_thread, True)
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)
                user32.AttachThreadInput(cur_thread, fg_thread, False)
            else:
                user32.BringWindowToTop(hwnd)
                user32.SetForegroundWindow(hwnd)

            try:
                user32.SwitchToThisWindow(hwnd, True)
            except Exception:
                pass

            activated = True
            break
        except Exception as ex:
            log.debug("[win_platform] bring_to_foreground attempt error: %s", ex)
            continue

    return activated


def get_monitor_refresh_rate(hwnd=None) -> int:
    """Return the display refresh rate (in Hz) of the active monitor or primary display."""
    import ctypes
    import ctypes.wintypes

    class DEVMODEW(ctypes.Structure):
        _fields_ = [
            ("dmDeviceName", ctypes.c_wchar * 32),
            ("dmSpecVersion", ctypes.c_ushort),
            ("dmDriverVersion", ctypes.c_ushort),
            ("dmSize", ctypes.c_ushort),
            ("dmDriverExtra", ctypes.c_ushort),
            ("dmFields", ctypes.c_ulong),
            ("dmOrientation", ctypes.c_short),
            ("dmPaperSize", ctypes.c_short),
            ("dmPaperLength", ctypes.c_short),
            ("dmPaperWidth", ctypes.c_short),
            ("dmScale", ctypes.c_short),
            ("dmCopies", ctypes.c_short),
            ("dmDefaultSource", ctypes.c_short),
            ("dmPrintQuality", ctypes.c_short),
            ("dmColor", ctypes.c_short),
            ("dmDuplex", ctypes.c_short),
            ("dmYResolution", ctypes.c_short),
            ("dmTTOption", ctypes.c_short),
            ("dmCollate", ctypes.c_short),
            ("dmFormName", ctypes.c_wchar * 32),
            ("dmLogPixels", ctypes.c_ushort),
            ("dmBitsPerPel", ctypes.c_ulong),
            ("dmPelsWidth", ctypes.c_ulong),
            ("dmPelsHeight", ctypes.c_ulong),
            ("dmDisplayFlags", ctypes.c_ulong),
            ("dmDisplayFrequency", ctypes.c_ulong),
        ]

    class MONITORINFOEXW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_ulong),
            ("rcMonitor", ctypes.wintypes.RECT),
            ("rcWork", ctypes.wintypes.RECT),
            ("dwFlags", ctypes.c_ulong),
            ("szDevice", ctypes.c_wchar * 32),
        ]

    try:
        user32 = ctypes.windll.user32
        target_hwnd = hwnd or user32.GetForegroundWindow()
        device_name = None
        if target_hwnd:
            hmon = user32.MonitorFromWindow(target_hwnd, 2)  # MONITOR_DEFAULTTONEAREST
            if hmon:
                mi = MONITORINFOEXW()
                mi.cbSize = ctypes.sizeof(MONITORINFOEXW)
                if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
                    device_name = mi.szDevice

        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        ENUM_CURRENT_SETTINGS = -1
        if user32.EnumDisplaySettingsW(device_name, ENUM_CURRENT_SETTINGS, ctypes.byref(dm)):
            freq = int(dm.dmDisplayFrequency)
            if freq > 0:
                return freq
    except Exception as ex:
        log.debug("[win_platform] get_monitor_refresh_rate error: %s", ex)

    # Fallback to primary display
    try:
        dm = DEVMODEW()
        dm.dmSize = ctypes.sizeof(DEVMODEW)
        if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)):
            freq = int(dm.dmDisplayFrequency)
            if freq > 0:
                return freq
    except Exception:
        pass

    return 60

