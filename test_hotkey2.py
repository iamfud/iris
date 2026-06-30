"""
Hotkey test v2 — works like Iris: captures the foreground BEFORE showing its own window,
then tries various methods to bring it back + send Ctrl+Shift+S.
"""
import tkinter as tk
import ctypes
import time
import threading

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

log_area = None

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")
    if log_area:
        root.after(0, lambda: log_area.insert(tk.END, msg + "\n"))

def get_window_title(hwnd):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value

captured_hwnd = None
captured_title = ""

def send_keys():
    for vk in [17, 16, 83]:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.015)
    for vk in [83, 16, 17]:
        user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.015)
    log("  >> Keys sent (Ctrl+Shift+S)")

ROOT = tk.Tk()
ROOT.withdraw()

# Step 1: Capture foreground BEFORE showing our window
captured_hwnd = user32.GetForegroundWindow()
captured_title = get_window_title(captured_hwnd)

import sys
sys.path.insert(0, "D:\\Derek\\D1\\app")

root = tk.Tk()
root.title("Hotkey Test v2")
root.geometry("600x600")
root.configure(bg="#202020")

log_area = tk.Text(root, bg="#111", fg="#0f0", font=("Consolas", 10),
                   height=30, width=80, relief="flat")
log_area.pack(padx=10, pady=10, fill=tk.BOTH, expand=True)

log(f"Captured foreground HWND: {captured_hwnd}")
log(f"Captured window title: {captured_title}")
log(f"IsWindow: {bool(user32.IsWindow(captured_hwnd))}")
log("")

def try_method(name, setup, teardown=None):
    def run():
        log(f"\n>>> {name}")
        if setup:
            setup()
        time.sleep(0.05)
        fg = user32.GetForegroundWindow()
        fg_title = get_window_title(fg)
        log(f"  Foreground now: {fg} = '{fg_title}'")
        send_keys()
        time.sleep(0.05)
        fg2 = user32.GetForegroundWindow()
        log(f"  After send, foreground: {fg2} = '{get_window_title(fg2)}'")
        if teardown:
            teardown()
    return run

def alt_press():
    user32.keybd_event(18, 0, 0, 0)
def alt_release():
    user32.keybd_event(18, 0, 2, 0)

def attach(target_tid=None):
    if target_tid is None:
        target_tid = user32.GetWindowThreadProcessId(captured_hwnd, None)
    cur_tid = kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(cur_tid, target_tid, True)
    return target_tid, cur_tid

def detach(target_tid, cur_tid):
    user32.AttachThreadInput(cur_tid, target_tid, False)

def make_btn(text, cmd):
    btn = tk.Button(root, text=text, command=lambda: threading.Thread(target=cmd, daemon=True).start(),
                    bg="#373737", fg="white", font=("Segoe UI", 9),
                    padx=10, pady=4, cursor="hand2")
    btn.pack(pady=2, padx=10, fill=tk.X)

make_btn("1. SetForegroundWindow + keys", try_method("Method 1: plain SetForegroundWindow",
    lambda: user32.SetForegroundWindow(captured_hwnd)))

make_btn("2. Alt-hack + SetForegroundWindow", try_method("Method 2: Alt hack",
    lambda: [alt_press(), user32.SetForegroundWindow(captured_hwnd), alt_release()]))

make_btn("3. AttachThreadInput + SetForegroundWindow", try_method("Method 3: AttachThreadInput",
    lambda: (lambda t, c: (user32.SetForegroundWindow(captured_hwnd), detach(t, c)))(*attach())))

make_btn("4. Alt + Attach + SetForegroundWindow", try_method("Method 4: Both",
    lambda: (alt_press(), user32.SetForegroundWindow(captured_hwnd), alt_release())))

make_btn("5. Alt + Attach (proper order)", try_method("Method 5: Alt then Attach then SetFG",
    lambda: (alt_press(), None, user32.SetForegroundWindow(captured_hwnd), alt_release())))

def method6():
    log("\n>>> Method 6: All-in-one (Alt+Attach+SetFG+Detach+Keys)")
    target_tid = user32.GetWindowThreadProcessId(captured_hwnd, None)
    cur_tid = kernel32.GetCurrentThreadId()
    user32.keybd_event(18, 0, 0, 0)  # Alt down
    user32.AttachThreadInput(cur_tid, target_tid, True)
    user32.SetForegroundWindow(captured_hwnd)
    user32.SetFocus(captured_hwnd)
    user32.AttachThreadInput(cur_tid, target_tid, False)
    user32.keybd_event(18, 0, 2, 0)  # Alt up
    time.sleep(0.05)
    fg = user32.GetForegroundWindow()
    log(f"  Foreground now: {fg} = '{get_window_title(fg)}'")
    send_keys()
    time.sleep(0.05)
    log(f"  After send, foreground: {user32.GetForegroundWindow()} = '{get_window_title(user32.GetForegroundWindow())}'")

make_btn("6. Complete: Alt+Attach+SetFG+Keys", method6)

def method7():
    log("\n>>> Method 7: main-thread Alt+Attach+SetFG+Keys")
    target_tid = user32.GetWindowThreadProcessId(captured_hwnd, None)
    cur_tid = kernel32.GetCurrentThreadId()
    user32.keybd_event(18, 0, 0, 0)
    user32.AttachThreadInput(cur_tid, target_tid, True)
    user32.SetForegroundWindow(captured_hwnd)
    user32.SetFocus(captured_hwnd)
    user32.AttachThreadInput(cur_tid, target_tid, False)
    user32.keybd_event(18, 0, 2, 0)
    time.sleep(0.05)
    fg = user32.GetForegroundWindow()
    log(f"  Foreground now: {fg} = '{get_window_title(fg)}'")
    send_keys()
    time.sleep(0.05)
    log(f"  After send, foreground: {user32.GetForegroundWindow()} = '{get_window_title(user32.GetForegroundWindow())}'")

make_btn("7. Main-thread: Alt+Attach+SetFG+Keys (NO extra thread)", method7)

log("")
log("=== HOW TO TEST ===")
log("1. Open Notepad or a text editor")
log("2. Position the test app window so you can see both")
log("3. With Notepad as the active window, press a method button here")
log("   (the test app captures the foreground BEFORE showing itself)")
log("4. Check if Notepad gains focus and receives Ctrl+Shift+S")
log("   (Ctrl+Shift+S in Notepad does nothing visible, but you can")
log("    type text and see if focus shifts to Notepad)")
log("")

root.mainloop()
