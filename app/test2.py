import time
import tkinter as tk
import ctypes
import pygetwindow as gw

# --- Windows Hardware Input Setup ---
SendInput = ctypes.windll.user32.SendInput
PUL = ctypes.POINTER(ctypes.c_ulong)

class KeyBdInput(ctypes.Structure):
    _fields_ = [("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class HardwareInput(ctypes.Structure):
    _fields_ = [("uMsg", ctypes.c_ulong),
                ("wParamL", ctypes.c_short),
                ("lParamH", ctypes.c_ushort)]

class MouseInput(ctypes.Structure):
    _fields_ = [("dx", ctypes.c_long),
                ("dy", ctypes.c_long),
                ("mouseData", ctypes.c_ulong),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", PUL)]

class Input_I(ctypes.Union):
    _fields_ = [("ki", KeyBdInput),
                ("mi", MouseInput),
                ("hi", HardwareInput)]

class Input(ctypes.Structure):
    _fields_ = [("type", ctypes.c_ulong),
                ("ii", Input_I)]

# DirectX Hardware Scan Codes
# Full list: https://millisecond.com
KEY_W = 0x11
KEY_S = 0x1F
KEY_LCTRL = 0x1D

def press_hardware_key(hex_key_code, duration=0.1):
    """Simulates a physical hardware key press and release"""
    # Key Down
    extra = ctypes.c_ulong(0)
    ii_ = Input_I()
    ii_.ki = KeyBdInput(0, hex_key_code, 0x0008, 0, ctypes.pointer(extra)) # 0x0008 = KEYEVENTF_SCANCODE
    x = Input(ctypes.c_ulong(1), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))
    
    time.sleep(duration)
    
    # Key Up
    ii_.ki = KeyBdInput(0, hex_key_code, 0x0008 | 0x0002, 0, ctypes.pointer(extra)) # 0x0002 = KEYEVENTF_KEYUP
    x = Input(ctypes.c_ulong(1), ii_)
    ctypes.windll.user32.SendInput(1, ctypes.pointer(x), ctypes.sizeof(x))

# --- Window Management & Trigger ---
def send_game_hotkey():
    root.withdraw()
    time.sleep(0.3)
    
    try:
        all_windows = gw.getAllWindows()
        visible_windows = [w for w in all_windows if w.title and w.visible]
        
        if visible_windows:
            target_window = visible_windows[0]
            target_window.activate()
            time.sleep(0.5) # Crucial for games to register the window focus switch
            
            # Example: Simulates pressing physical 'W' key in a game
            press_hardware_key(KEY_W, duration=0.2)
            print(f"Sent hardware key to: {target_window.title}")
            
    except Exception as e:
        print(f"Error: {e}")
    finally:
        root.deiconify()

# --- GUI ---
root = tk.Tk()
root.title("Game Input Fix")
root.geometry("250x100")
root.attributes('-topmost', True)

tk.Button(
    root, text="🎮 Send Game Key", command=send_game_hotkey,
    font=("Arial", 12, "bold"), bg="#111", fg="#0f0", padx=10, pady=10
).pack(expand=True)

root.mainloop()
