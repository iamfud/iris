"""Shared sound playback module.

Exposes named sounds (remind, annoy, melody) for use by alarm system,
plugins, and any other component.  Plays MP3 via PowerShell MediaPlayer
on a background thread.  Stop terminates the player process instantly.
"""

import logging
import os
import subprocess
import sys
import threading

log = logging.getLogger("iris.sound")

if getattr(sys, "frozen", False):
    _media_dir = os.path.join(sys._MEIPASS, "media")
else:
    _media_dir = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "media")

SOUNDS = {
    "remind":  os.path.join(_media_dir, "remind.mp3"),
    "annoy":   os.path.join(_media_dir, "annoy.mp3"),
    "melody":  os.path.join(_media_dir, "melody.mp3"),
}

_proc = None
_lock = threading.Lock()

_CREATE_NO_WINDOW = 0x08000000


def list_sounds():
    """Return list of available sound names."""
    return list(SOUNDS.keys())


def play(name="remind", loop=False):
    """Play a named sound. Stops any currently playing sound first."""
    path = SOUNDS.get(name)
    if not path or not os.path.isfile(path):
        log.warning("[sound] file not found: %s (%s)", name, path)
        return False
    stop()
    try:
        norm_path = os.path.abspath(path).replace("\\", "/")
        ps = (
            "Add-Type -AssemblyName PresentationCore; "
            "$p = New-Object System.Windows.Media.MediaPlayer; "
            f"$p.Open([Uri]::new('{norm_path}')); "
            "$p.Play(); "
            "Start-Sleep -Milliseconds 300; "
            "$deadline = (Get-Date).AddSeconds(3.5); "
            "while ((Get-Date) -lt $deadline) { "
            "  if ($p.NaturalDuration.HasTimeSpan -and $p.Position -ge $p.NaturalDuration.TimeSpan) { break }; "
            "  Start-Sleep -Milliseconds 100 "
            "}"
        )
        with _lock:
            global _proc
            _proc = subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps],
                creationflags=_CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        return True
    except Exception as e:
        log.warning("[sound] play failed: %s", e)
        return False


def play_one_shot(name="remind"):
    """Play an alert/notification sound once without looping."""
    return play(name=name, loop=False)


def stop():
    """Stop the currently playing sound by killing the player process."""
    with _lock:
        global _proc
        if _proc:
            try:
                _proc.kill()
            except Exception:
                pass
            _proc = None


def is_playing():
    """Return True if a sound is currently playing."""
    with _lock:
        if _proc is None:
            return False
        return _proc.poll() is None
