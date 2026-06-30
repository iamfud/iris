"""Test RTSS shared memory — dump all hooked processes + FPS + foreground check."""
import ctypes
import struct
import time

def foreground_exe():
    try:
        hwnd = ctypes.windll.user32.GetForegroundWindow()
        pid = ctypes.c_ulong()
        ctypes.windll.user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        import psutil
        return psutil.Process(pid.value).exe()
    except Exception:
        return ""

_MAP = "RTSSSharedMemoryV2"
_READ = 0x0004
_SIG = 0x52545353
_E_NAME = 4
_E_TIME0 = 268
_E_TIME1 = 272
_E_FRAMES = 276
_E_FPS = 812
_H_ENTRY_SZ = 8
_H_ARR_OFF = 12
_H_ARR_CNT = 16

k = ctypes.windll.kernel32
k.OpenFileMappingW.restype = ctypes.c_void_p
k.OpenFileMappingW.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_wchar_p]
k.MapViewOfFile.restype = ctypes.c_void_p
k.MapViewOfFile.argtypes = [ctypes.c_void_p, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_uint32, ctypes.c_size_t]
k.UnmapViewOfFile.argtypes = [ctypes.c_void_p]
k.CloseHandle.argtypes = [ctypes.c_void_p]
k.GetTickCount.restype = ctypes.c_uint32

h = k.OpenFileMappingW(_READ, False, _MAP)
if not h:
    print("RTSS not running — no shared memory.")
    exit(1)

try:
    base = k.MapViewOfFile(h, _READ, 0, 0, 0)
    if not base:
        print("Failed to map RTSS memory.")
        exit(1)
    try:
        sig = int.from_bytes(ctypes.string_at(base, 4), "little")
        print(f"Signature: 0x{sig:08X} (expected 0x{_SIG:08X})")
        if sig != _SIG:
            print("Bad signature — not RTSS shared memory.")
            exit(1)

        entry_sz = int.from_bytes(ctypes.string_at(base + _H_ENTRY_SZ, 4), "little")
        arr_off = int.from_bytes(ctypes.string_at(base + _H_ARR_OFF, 4), "little")
        arr_cnt = int.from_bytes(ctypes.string_at(base + _H_ARR_CNT, 4), "little")
        print(f"Entry size: {entry_sz}, Array offset: {arr_off}, Count: {arr_cnt}")

        if not entry_sz or not arr_cnt:
            print("No entries.")
            exit(0)

        print(f"\n{'#':<4} {'Process':<30} {'FPS':<8} {'Age(ms)':<8} {'Frames':<8}")
        print("-" * 60)
        now_ms = k.GetTickCount()

        for i in range(min(arr_cnt, 128)):
            e = base + arr_off + i * entry_sz
            name = ctypes.string_at(e + _E_NAME, 260).split(b"\x00")[0].decode("utf-8", errors="ignore")
            if not name:
                continue
            time1 = int.from_bytes(ctypes.string_at(e + _E_TIME1, 4), "little")
            age = (now_ms - time1) & 0xFFFFFFFF
            fps = 0.0
            frames = 0
            if entry_sz > _E_FPS + 4:
                fps_raw = int.from_bytes(ctypes.string_at(e + _E_FPS, 4), "little")
                if fps_raw:
                    fps = fps_raw / 1000.0
            if not fps and entry_sz > _E_FRAMES + 4:
                frames = int.from_bytes(ctypes.string_at(e + _E_FRAMES, 4), "little")
                time0 = int.from_bytes(ctypes.string_at(e + _E_TIME0, 4), "little")
                dt = time1 - time0
                if frames > 0 and dt > 0:
                    fps = frames * 1000.0 / dt
            active = age <= 3000
            status = "ACTIVE" if active else "STALE"
            match = "  <-- FOREGROUND" if name and active and name.lower() == foreground_exe().lower() else ""
            print(f"{i:<4} {name:<30} {fps:<8.1f} {age:<8} {frames:<8}  {status}{match}")

    finally:
        k.UnmapViewOfFile(base)
finally:
    k.CloseHandle(h)
