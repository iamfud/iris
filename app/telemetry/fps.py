"""Game FPS tracking via PresentMon ETW trace with RTSS shared memory fallback.

RTSS is a passive read-only fallback — Iris NEVER starts, requires, or manages RTSS.
PresentMon (bundled in lib/) is the primary standalone capture method.
"""

import collections
import ctypes
import logging
import math
import os
import subprocess
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from telemetry.paths import get_presentmon_exe_path

log = logging.getLogger("iris.telemetry.fps")

# Desktop utilities / background apps that hook 3D APIs or render with GPU but aren't games
IGNORED_BACKGROUND = {
    "camostudio.exe", "openrgb.exe", "nzxt cam.exe", "whatsapp.root.exe",
    "chatgpt.exe", "chrome.exe", "msedge.exe", "explorer.exe", "dwm.exe",
    "taskmgr.exe", "python.exe", "pythonw.exe", "iris.exe", "cam_helper.exe",
    "discord.exe", "spotify.exe", "slack.exe", "teams.exe", "steam.exe",
    "steamwebhelper.exe", "devenv.exe", "code.exe", "epicgameslauncher.exe",
    "obs64.exe", "obs32.exe", "overwolf.exe", "overwolfbrowser.exe", "medal.exe",
    "geforcenow.exe", "furmark_gui.exe", "windowsterminal.exe", "applicationframehost.exe",
    "shellexperiencehost.exe", "searchhost.exe", "startmenuexperiencehost.exe",
    "textinputhost.exe", "systemsettings.exe", "powershell.exe", "pwsh.exe",
    "cmd.exe", "conhost.exe", "msedgewebview2.exe", "nvidia share.exe", "nvcontainer.exe",
}



def _calc_fps_and_low(intervals: List[float]) -> Tuple[Optional[float], Optional[float], Optional[float]]:
    """Given presentation intervals in ms, returns (avg_fps, fps_1pct_low, avg_frametime_ms)."""
    if not intervals:
        return None, None, None

    valid = [ms for ms in intervals if 0.1 <= ms <= 1000.0]
    if not valid:
        return None, None, None

    avg_ms = sum(valid) / len(valid)
    avg_fps = round(1000.0 / avg_ms, 1) if avg_ms > 0 else None

    if len(valid) >= 10:
        sorted_desc = sorted(valid, reverse=True)
        count = max(1, int(math.ceil(len(sorted_desc) * 0.01)))
        worst_avg_ms = sum(sorted_desc[:count]) / count
        fps_1pct_low = round(1000.0 / worst_avg_ms, 1) if worst_avg_ms > 0 else None
    else:
        fps_1pct_low = avg_fps

    return avg_fps, fps_1pct_low, round(avg_ms, 1)


def _resolve_name_from_pid(pid: int) -> Optional[str]:
    """Attempt to resolve a process name from its PID using psutil."""
    try:
        import psutil
        return psutil.Process(pid).name()
    except Exception:
        return None


class FpsTracker:
    """Captures real-time Game FPS using standalone PresentMon with passive RTSS fallback.

    Priority order:
      1. RTSS shared memory — if RTSS happens to already be running (passive read only,
         Iris never starts or manages RTSS).
      2. PresentMon ETW capture (bundled lib/PresentMon-x64.exe).
    """

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()

        self._apps: Dict[int, Dict[str, Any]] = {}
        self._rtss_intervals: collections.deque = collections.deque(maxlen=300)
        self._rtss_last_t1: int = 0

        pmon_path = get_presentmon_exe_path()
        if os.path.isfile(pmon_path):
            self._start_presentmon(pmon_path)
        else:
            log.warning("[telemetry.fps] PresentMon not found at: %s", pmon_path)

    def _read_rtss(self) -> Optional[Dict[str, Any]]:
        """Passively reads FPS from RTSS shared memory if RTSS is already running.

        This is a pure read — Iris never starts, restarts, or manages RTSS.
        If the shared memory segment is absent, returns None immediately.
        """
        try:
            import struct
            kernel32 = ctypes.windll.kernel32
            user32 = ctypes.windll.user32

            kernel32.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
            kernel32.OpenFileMappingW.restype = ctypes.c_void_p
            kernel32.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]
            kernel32.MapViewOfFile.restype = ctypes.c_void_p
            kernel32.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
            kernel32.CloseHandle.argtypes = [ctypes.c_void_p]

            FILE_MAP_READ = 0x0004
            h_map = kernel32.OpenFileMappingW(FILE_MAP_READ, False, "RTSSSharedMemoryV2")
            if not h_map:
                h_map = kernel32.OpenFileMappingW(FILE_MAP_READ, False, "RTSSSharedMemory")
            if not h_map:
                # RTSS is not running — silently return, do not attempt to start it
                return None

            ptr = kernel32.MapViewOfFile(h_map, FILE_MAP_READ, 0, 0, 0)
            if not ptr:
                kernel32.CloseHandle(h_map)
                return None

            hdr_raw = bytes((ctypes.c_ubyte * 20).from_address(ptr))
            sig, ver, app_size, app_offset, app_margin = struct.unpack("<IIIII", hdr_raw)

            if sig not in (0x52545353, 0xDEAD) or app_size == 0 or app_margin == 0:
                kernel32.UnmapViewOfFile(ptr)
                kernel32.CloseHandle(h_map)
                return None

            fg_hwnd = user32.GetForegroundWindow()
            fg_pid_c = ctypes.c_uint32(0)
            if fg_hwnd:
                user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(fg_pid_c))
            fg_pid = fg_pid_c.value

            current_tick = kernel32.GetTickCount()

            active_app = None
            highest_fps_app = None

            for i in range(min(app_margin, 256)):
                off = app_offset + i * app_size
                read_len = min(app_size, 1024)
                if read_len < 284:
                    continue
                raw = bytes((ctypes.c_ubyte * read_len).from_address(ptr + off))
                pid = struct.unpack("<I", raw[:4])[0]
                if pid == 0:
                    continue

                raw_name = raw[4:264].split(b"\x00")[0].decode("latin-1", errors="ignore")
                exe_name = raw_name.replace("/", "\\").split("\\")[-1]
                exe_lower = exe_name.lower()

                flags, t0, t1, frames, ftime = struct.unpack("<IIIII", raw[264:284])

                time_since_present = (current_tick - t1) & 0xFFFFFFFF
                if t1 > 0 and time_since_present > 3500:
                    continue

                fps = 0.0
                if read_len >= 816:
                    fps_raw = struct.unpack("<I", raw[812:816])[0]
                    if fps_raw > 0:
                        fps = fps_raw / 1000.0
                if fps <= 0.0 and read_len >= 824:
                    fps_avg_raw = struct.unpack("<I", raw[820:824])[0]
                    if fps_avg_raw > 0:
                        fps = fps_avg_raw / 1000.0
                if fps <= 0.0:
                    dt = (t1 - t0) & 0xFFFFFFFF
                    if dt > 0 and frames > 0:
                        fps = 1000.0 * frames / dt
                    elif ftime > 0 and ftime < 1_000_000:
                        fps = 1_000_000.0 / ftime

                ftime_ms = ftime / 1000.0 if ftime > 0 else (1000.0 / fps if fps > 0 else 0.0)

                is_utility = exe_lower in IGNORED_BACKGROUND
                if is_utility:
                    continue

                if fps > 1.0:
                    candidate = {
                        "fps": round(fps, 1),
                        "game_name": exe_name,
                        "frametime_ms": round(ftime_ms, 1),
                        "_t1": t1,
                        "_ftime_ms": ftime_ms,
                    }
                    if pid == fg_pid:
                        active_app = candidate
                        break
                    elif not is_utility:
                        if highest_fps_app is None or fps > highest_fps_app["fps"]:
                            highest_fps_app = candidate

            kernel32.UnmapViewOfFile(ptr)
            kernel32.CloseHandle(h_map)

            app_result = active_app or highest_fps_app
            if app_result:
                t1_val = app_result.pop("_t1", 0)
                f_val = app_result.pop("_ftime_ms", 0.0)
                if t1_val > 0 and t1_val != self._rtss_last_t1:
                    self._rtss_last_t1 = t1_val
                    if 0.1 <= f_val <= 1000.0:
                        self._rtss_intervals.append(f_val)

                r_fps, r_low, r_ms = _calc_fps_and_low(list(self._rtss_intervals))
                if r_fps is not None:
                    if app_result.get("fps", 0) <= 0:
                        app_result["fps"] = r_fps
                    app_result["fps_1pct_low"] = r_low
                    app_result["frametime_ms"] = r_ms
                else:
                    app_result["fps_1pct_low"] = app_result.get("fps")
            else:
                self._rtss_intervals.clear()

            return app_result
        except Exception:
            return None

    def _drain_stderr(self):
        if not self._proc or not self._proc.stderr:
            return
        try:
            for _ in iter(self._proc.stderr.readline, ""):
                if self._stop_event.is_set():
                    break
        except Exception:
            pass

    def _start_presentmon(self, pmon_path: str):
        try:
            cmd = [
                pmon_path,
                "--stop_existing_session",
                "--output_stdout",
                "--no_track_input",
                "--no_track_gpu",
                "--exclude", "python.exe",
                "--exclude", "pythonw.exe",
                "--exclude", "msedge.exe",
                "--exclude", "chrome.exe",
                "--exclude", "dwm.exe",
                "--exclude", "explorer.exe",
                "--exclude", "Taskmgr.exe",
                "--exclude", "Discord.exe",
                "--exclude", "Spotify.exe",
                "--exclude", "steamwebhelper.exe",
                "--exclude", "WindowsTerminal.exe",
                "--exclude", "ApplicationFrameHost.exe",
                "--exclude", "ShellExperienceHost.exe",
                "--exclude", "SearchHost.exe",
                "--exclude", "StartMenuExperienceHost.exe",
                "--exclude", "TextInputHost.exe",
                "--exclude", "SystemSettings.exe",
                "--exclude", "powershell.exe",
                "--exclude", "pwsh.exe",
                "--exclude", "cmd.exe",
                "--exclude", "conhost.exe",
                "--exclude", "msedgewebview2.exe",
            ]

            creationflags = 0x08000000  # CREATE_NO_WINDOW
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
                creationflags=creationflags,
            )
            self._thread = threading.Thread(target=self._reader_loop, daemon=True, name="telemetry-pmon")
            self._thread.start()
            self._err_thread = threading.Thread(target=self._drain_stderr, daemon=True, name="telemetry-pmon-err")
            self._err_thread.start()
            log.info("[telemetry.fps] PresentMon started (pid=%s)", self._proc.pid)
        except Exception as ex:
            log.debug("[telemetry.fps] PresentMon start error: %s", ex)
            self._proc = None

    def _reader_loop(self):
        if not self._proc or not self._proc.stdout:
            return

        col_app = 0
        col_pid = 1
        col_between = 9  # Fallback index if parsing glitches

        try:
            for line in iter(self._proc.stdout.readline, ""):
                if self._stop_event.is_set():
                    break
                line = line.replace("\x00", "").strip()
                if not line:
                    continue

                # Strip all structural padding out of the parts list immediately
                parts = [p.strip() for p in line.split(",")]

                if "Application" in parts:
                    col_app = parts.index("Application")
                    if "ProcessID" in parts:
                        col_pid = parts.index("ProcessID")
                    if "FrameTime" in parts:
                        col_between = parts.index("FrameTime")
                    elif "msBetweenPresents" in parts:
                        col_between = parts.index("msBetweenPresents")
                    elif "MsBetweenPresents" in parts:
                        col_between = parts.index("MsBetweenPresents")
                    continue

                max_col = max(col_app, col_pid, col_between)
                if len(parts) > max_col:
                    try:
                        app = parts[col_app]
                        pid = int(parts[col_pid])
                        ms_between = float(parts[col_between])

                        # When running non-elevated, PresentMon outputs "<unknown>" for the
                        # Application column on elevated/cross-session processes.
                        # Resolve the real name from the PID via psutil instead of discarding.
                        if not app or app.startswith("<"):
                            resolved = _resolve_name_from_pid(pid)
                            if resolved:
                                app = resolved
                            else:
                                continue  # Cannot identify process — skip

                        if app.lower() in IGNORED_BACKGROUND:
                            continue

                        # Valid frame interval: 0.1 ms (10 000 FPS cap) to 2 000 ms (0.5 FPS floor)
                        if 0.1 <= ms_between <= 2000.0:
                            now = time.time()
                            with self._lock:
                                if pid not in self._apps:
                                    self._apps[pid] = {
                                        "name": app,
                                        "intervals": collections.deque(maxlen=300),
                                        "last_ts": now,
                                    }
                                entry = self._apps[pid]
                                entry["name"] = app
                                entry["intervals"].append(ms_between)
                                entry["last_ts"] = now
                    except (ValueError, IndexError):
                        pass
        except Exception:
            pass

    def get_stats(self) -> Dict[str, Any]:
        _null = {"fps": None, "fps_1pct_low": None, "frametime_ms": None, "game_name": None}

        # Priority 1: Passive RTSS read (only if RTSS is already running)
        rtss = self._read_rtss()
        if rtss and rtss.get("fps", 0) > 0:
            return rtss

        # Priority 2: PresentMon ETW stats
        with self._lock:
            now = time.time()
            # Prune stale apps (no frames in last 3.5 seconds)
            stale_pids = [pid for pid, info in self._apps.items() if now - info["last_ts"] > 3.5]
            for pid in stale_pids:
                del self._apps[pid]

            if not self._apps:
                return _null

            # Prefer the foreground window's process
            fg_pid = 0
            try:
                user32 = ctypes.windll.user32
                fg_hwnd = user32.GetForegroundWindow()
                if fg_hwnd:
                    fg_pid_c = ctypes.c_uint32(0)
                    user32.GetWindowThreadProcessId(fg_hwnd, ctypes.byref(fg_pid_c))
                    fg_pid = fg_pid_c.value
            except Exception:
                pass

            fg_name = ""
            if fg_pid:
                fg_name = (_resolve_name_from_pid(fg_pid) or "").lower()

            if fg_name and fg_name in IGNORED_BACKGROUND:
                # Foreground is explicitly a desktop tool, shell, or terminal — user is not gaming
                return _null

            target_app = None
            if fg_pid and fg_pid in self._apps:
                app_candidate = self._apps[fg_pid]
                if app_candidate.get("name", "").lower() not in IGNORED_BACKGROUND:
                    target_app = app_candidate
            else:
                # Foreground is desktop/Iris overlay — pick the most recently active tracked game
                candidates = [
                    a for a in self._apps.values()
                    if a.get("name", "").lower() not in IGNORED_BACKGROUND
                ]
                if candidates:
                    target_app = max(candidates, key=lambda a: a["last_ts"])

            if not target_app or not target_app.get("intervals"):
                return _null


            # No frame in the last 2 s → game is paused or idle
            if now - target_app["last_ts"] > 2.0:
                return _null

            intervals = list(target_app["intervals"])
            fps, fps_low, avg_ms = _calc_fps_and_low(intervals)

            raw_name = target_app["name"]
            game_name = raw_name[:-4] if raw_name.lower().endswith(".exe") else raw_name
            if game_name.islower():
                game_name = game_name.capitalize()

            return {
                "fps": fps,
                "fps_1pct_low": fps_low,
                "frametime_ms": avg_ms,
                "game_name": game_name,
            }

    def close(self):
        self._stop_event.set()
        if self._proc:
            try:
                self._proc.terminate()
                self._proc.wait(timeout=1.0)
            except Exception:
                try:
                    self._proc.kill()
                except Exception:
                    pass
            self._proc = None
