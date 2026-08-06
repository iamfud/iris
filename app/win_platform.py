"""Iris — Windows platform utilities."""

import logging

log = logging.getLogger("iris.platform")




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



def _extract_via_ps(icon_path, size=64):
    """Extract an app icon via PowerShell.
    
    Path is passed via IRIS_ICON_PATH env var (not command-line interpolation)
    to prevent injection.  Returns a PIL Image or None.
    """
    import os
    import subprocess
    import tempfile
    from PIL import Image

    if not icon_path or not os.path.isfile(icon_path):
        return None

    try:
        fd, tmp = tempfile.mkstemp(suffix=".png")
        os.close(fd)

        env = os.environ.copy()
        env["IRIS_ICON_PATH"] = icon_path
        env["IRIS_ICON_OUT"] = tmp

        # Both paths are supplied through environment variables — user input
        # is never interpolated into the command.
        ps = (
            'Add-Type -AssemblyName System.Drawing; '
            '$p = $env:IRIS_ICON_PATH; '
            '$o = $env:IRIS_ICON_OUT; '
            'try { '
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
            return img

        os.unlink(tmp)
    except Exception as e:
        log.debug("[extract] PS icon extraction failed: %s", e)
        try:
            os.unlink(tmp)
        except Exception:
            pass
    return None

