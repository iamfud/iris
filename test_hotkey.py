"""Standalone test for hotkey sending — click any button to try sending Ctrl+Shift+S to the last active window."""
import tkinter as tk
import ctypes
import time
import threading

user32 = ctypes.windll.user32

user32.SetForegroundWindow.argtypes = [ctypes.c_void_p]
user32.SetForegroundWindow.restype = ctypes.c_bool
user32.IsWindow.argtypes = [ctypes.c_void_p]
user32.IsWindow.restype = ctypes.c_bool
user32.GetWindowThreadProcessId.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, ctypes.c_ulong, ctypes.c_ulong]
user32.GetForegroundWindow.restype = ctypes.c_void_p
user32.GetCurrentThreadId = ctypes.windll.kernel32.GetCurrentThreadId
user32.GetCurrentThreadId.restype = ctypes.c_ulong

VK_ALT = 18
VK_CTRL = 17
VK_SHIFT = 16
VK_S = 83

saved_hwnd = None

def log(msg):
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")

def method1_direct():
    """Plain SetForegroundWindow + keybd_event."""
    target = saved_hwnd
    log(f"Method 1 — target={target} IsWindow={bool(user32.IsWindow(target))}")
    user32.SetForegroundWindow(target)
    time.sleep(0.05)
    fg = user32.GetForegroundWindow()
    log(f"  Foreground now: {fg}")
    send_keys()

def method2_alt_hack():
    """Alt-key workaround + SetForegroundWindow + keybd_event."""
    target = saved_hwnd
    log(f"Method 2 — target={target}")
    user32.keybd_event(VK_ALT, 0, 0, 0)
    user32.SetForegroundWindow(target)
    user32.keybd_event(VK_ALT, 0, 2, 0)
    time.sleep(0.05)
    fg = user32.GetForegroundWindow()
    log(f"  Foreground now: {fg}")
    send_keys()

def method3_attach_thread():
    """AttachThreadInput + SetForegroundWindow + keybd_event."""
    target = saved_hwnd
    log(f"Method 3 — target={target}")
    target_tid = user32.GetWindowThreadProcessId(target, None)
    cur_tid = user32.GetCurrentThreadId()
    log(f"  target_tid={target_tid} cur_tid={cur_tid}")
    user32.AttachThreadInput(cur_tid, target_tid, True)
    user32.SetForegroundWindow(target)
    user32.AttachThreadInput(cur_tid, target_tid, False)
    time.sleep(0.05)
    fg = user32.GetForegroundWindow()
    log(f"  Foreground now: {fg}")
    send_keys()

def method4_both():
    """Alt hack + AttachThreadInput + SetForegroundWindow."""
    target = saved_hwnd
    log(f"Method 4 — target={target}")
    user32.keybd_event(VK_ALT, 0, 0, 0)
    target_tid = user32.GetWindowThreadProcessId(target, None)
    cur_tid = user32.GetCurrentThreadId()
    user32.AttachThreadInput(cur_tid, target_tid, True)
    user32.SetForegroundWindow(target)
    user32.AttachThreadInput(cur_tid, target_tid, False)
    user32.keybd_event(VK_ALT, 0, 2, 0)
    time.sleep(0.05)
    fg = user32.GetForegroundWindow()
    log(f"  Foreground now: {fg}")
    send_keys()

def method5_post():
    """PostMessage WM_KEYDOWN/WM_KEYUP directly to target."""
    target = saved_hwnd
    log(f"Method 5 — PostMessage to target={target}")
    for vk in [VK_CTRL, VK_SHIFT, VK_S]:
        user32.PostMessageW(target, 0x0100, vk, 0)
        time.sleep(0.01)
    for vk in [VK_S, VK_SHIFT, VK_CTRL]:
        user32.PostMessageW(target, 0x0101, vk, 0)
        time.sleep(0.01)
    log("  Sent via PostMessage")

def method6_attach_main():
    """AttachThreadInput on main thread (not after)."""
    target = saved_hwnd
    log(f"Method 6 — main thread attach target={target}")
    target_tid = user32.GetWindowThreadProcessId(target, None)
    cur_tid = user32.GetCurrentThreadId()
    user32.AttachThreadInput(cur_tid, target_tid, True)
    ret = user32.SetForegroundWindow(target)
    log(f"  SetForegroundWindow returned: {ret}")
    user32.SetFocus(target)
    user32.AttachThreadInput(cur_tid, target_tid, False)
    time.sleep(0.05)
    fg = user32.GetForegroundWindow()
    log(f"  Foreground now: {fg}")
    send_keys()
    log(f"  After send, foreground: {user32.GetForegroundWindow()}")

def method7_sendinput():
    """SendInput with KEYBDINPUT structures."""
    target = saved_hwnd
    log(f"Method 7 — SendInput, target={target}")
    class KEYBDINPUT(ctypes.Structure):
        _fields_ = [("wVk", ctypes.c_ushort), ("wScan", ctypes.c_ushort),
                    ("dwFlags", ctypes.c_ulong), ("time", ctypes.c_ulong),
                    ("dwExtraInfo", ctypes.c_void_p)]
    class INPUT(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]
        _fields_ = [("type", ctypes.c_ulong), ("union", _U)]

    INPUT_KEYBOARD = 1
    KEYEVENTF_KEYUP = 0x0002

    def send(vk, press=True):
        ki = KEYBDINPUT(vk, 0, 0 if press else KEYEVENTF_KEYUP, 0, None)
        inp = INPUT(INPUT_KEYBOARD, INPUT._U(ki=ki))
        user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(inp))
        time.sleep(0.015)

    user32.keybd_event(VK_ALT, 0, 0, 0)
    user32.SetForegroundWindow(target)
    user32.keybd_event(VK_ALT, 0, 2, 0)
    time.sleep(0.05)
    for vk in [VK_CTRL, VK_SHIFT, VK_S]:
        send(vk, True)
    for vk in [VK_S, VK_SHIFT, VK_CTRL]:
        send(vk, False)
    log("  Sent via SendInput")

def send_keys():
    for vk in [VK_CTRL, VK_SHIFT, VK_S]:
        user32.keybd_event(vk, 0, 0, 0)
        time.sleep(0.015)
    for vk in [VK_S, VK_SHIFT, VK_CTRL]:
        user32.keybd_event(vk, 0, 2, 0)
        time.sleep(0.015)
    log("  Keys sent (Ctrl+Shift+S)")

root = tk.Tk()
root.title("Hotkey Test")
root.geometry("500x500")
root.configure(bg="#202020")

label = tk.Label(root, text="Click a method, then switch to Notepad or a text editor\nand see if Ctrl+Shift+S types an 's' or triggers Save",
                 bg="#202020", fg="white", font=("Segoe UI", 10))
label.pack(pady=10)

def make_btn(text, cmd):
    btn = tk.Button(root, text=text, command=cmd,
                    bg="#373737", fg="white", font=("Segoe UI", 9),
                    padx=10, pady=5, cursor="hand2")
    btn.pack(pady=3, padx=10, fill=tk.X)

def capture():
    global saved_hwnd
    saved_hwnd = user32.GetForegroundWindow()
    label2.config(text=f"Captured: {saved_hwnd}")

def run_in_thread(cmd):
    threading.Thread(target=cmd, daemon=True).start()

capture_btn = tk.Button(root, text="CAPTURE FOREGROUND", command=capture,
                        bg="#2b2b2b", fg="#00ff88", font=("Segoe UI", 9, "bold"),
                        padx=10, pady=5)
capture_btn.pack(pady=5)

label2 = tk.Label(root, text="Captured: None", bg="#202020", fg="#888", font=("Segoe UI", 9))
label2.pack()

tk.Frame(root, bg="#373737", height=1).pack(fill=tk.X, pady=5)

update_btn = tk.Button(root, text="UPDATE CAPTURE (before clicking a method)", command=capture,
                       bg="#2b2b2b", fg="#888", font=("Segoe UI", 8))
update_btn.pack(pady=2)

make_btn("1. SetForegroundWindow (thread)", lambda: run_in_thread(method1_direct))
make_btn("2. Alt-hack + SetForegroundWindow (thread)", lambda: run_in_thread(method2_alt_hack))
make_btn("3. AttachThreadInput (thread)", lambda: run_in_thread(method3_attach_thread))
make_btn("4. Both Alt + Attach (thread)", lambda: run_in_thread(method4_both))
make_btn("5. PostMessage (no focus change)", lambda: run_in_thread(method5_post))
make_btn("6. AttachThreadInput (main thread via after)", lambda: root.after(50, method6_attach_main))
make_btn("7. SendInput + Alt hack (thread)", lambda: run_in_thread(method7_sendinput))

tk.Label(root, text="Test: 1) Click CAPTURE while in another window  2) Click back here  3) Click a method",
         bg="#202020", fg="#666", font=("Segoe UI", 8)).pack(pady=10)

root.mainloop()
