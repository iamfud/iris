"""
Debug hotkey sending — fully automatic. Run this while another window is visible.

Opens Notepad to have a known test target, captures it, then tries methods.
"""
import ctypes
import time
import subprocess
import sys

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32

user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
user32.SetForegroundWindow.restype = ctypes.c_bool
user32.IsWindow.argtypes = [ctypes.c_void_p]
user32.IsWindow.restype = ctypes.c_bool
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong, ctypes.c_ulong]
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetWindowTextW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p, ctypes.c_int]
user32.GetWindowTextW.restype = ctypes.c_int
user32.GetWindowThreadProcessId.restype = ctypes.c_ulong

def get_title(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value

def find_notepad():
    """Find Notepad window by class."""
    user32.FindWindowW.argtypes = [ctypes.c_wchar_p, ctypes.c_wchar_p]
    user32.FindWindowW.restype = ctypes.c_void_p
    return user32.FindWindowW("Notepad", None)

def send_keys(method_name):
    for vk in [17, 16, 83]:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.015)
    for vk in [83, 16, 17]:
        user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.015)
    print(f"  [{method_name}] Keys sent")

def try_method(name, focus_fn):
    fg = user32.GetForegroundWindow()
    print(f"\n[{name}]")
    print(f"  Foreground before: {fg} = '{get_title(fg)[:60]}'")
    focus_fn()
    time.sleep(0.1)
    fg2 = user32.GetForegroundWindow()
    print(f"  Foreground after:  {fg2} = '{get_title(fg2)[:60]}'")
    print(f"  Changed? {fg2 != fg}")
    send_keys(name)
    time.sleep(0.1)
    fg3 = user32.GetForegroundWindow()
    print(f"  Foreground final:  {fg3} = '{get_title(fg3)[:60]}'")

# Open Notepad as a test target
print("Opening Notepad...")
subprocess.Popen("notepad.exe")
time.sleep(2)

npad = find_notepad()
print(f"Notepad HWND: {npad}")
print(f"Notepad title: '{get_title(npad)}'")
print(f"IsWindow: {bool(user32.IsWindow(npad))}")
print()

if not npad:
    print("ERROR: Could not find Notepad")
    sys.exit(1)

# Make Notepad foreground first (so we have a clean state)
print("Making Notepad foreground...")
user32.SetForegroundWindow(npad)
time.sleep(0.3)
print(f"Foreground now: {user32.GetForegroundWindow()} = '{get_title(user32.GetForegroundWindow())[:60]}'")
print()

# Now Notepad should be foreground. Capture it as target.
target = npad
print(f"Target = Notepad ({target})")
print()

# Method 1: Plain SetForegroundWindow + keys
# First make something else foreground (this console)
# Actually, the console is the foreground since we're running from cmd/powershell
try_method("1. SetFG", lambda: user32.SetForegroundWindow(target))

# Method 2: Alt-hack
try_method("2. Alt+SetFG", lambda: (
    user32.keybd_event(18, 0, 0, 0),
    user32.SetForegroundWindow(target),
    user32.keybd_event(18, 0, 2, 0)
))

# Method 3: AttachThreadInput
def attach_method():
    tid = user32.GetWindowThreadProcessId(target, None)
    cur = kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(cur, tid, True)
    user32.SetForegroundWindow(target)
    user32.SetFocus(target)
    user32.AttachThreadInput(cur, tid, False)

try_method("3. AttachThreadInput", attach_method)

# Method 4: Alt + Attach
def attach_alt():
    tid = user32.GetWindowThreadProcessId(target, None)
    cur = kernel32.GetCurrentThreadId()
    user32.keybd_event(18, 0, 0, 0)
    user32.AttachThreadInput(cur, tid, True)
    user32.SetForegroundWindow(target)
    user32.SetFocus(target)
    user32.AttachThreadInput(cur, tid, False)
    user32.keybd_event(18, 0, 2, 0)

try_method("4. Alt+Attach", attach_alt)

# Method 5: BringWindowToTop + SetForegroundWindow
try_method("5. BringToTop+SetFG", lambda: (
    user32.BringWindowToTop(target),
    user32.SetForegroundWindow(target),
    user32.SetActiveWindow(target),
))

# Method 6: SwitchToThisWindow (powerful but older API)
try_method("6. SwitchToThisWindow", lambda: (
    user32.SwitchToThisWindow(target, True),
    time.sleep(0.05),
    user32.SetFocus(target),
))

print("\n=== Done ===")
