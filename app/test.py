import time
import tkinter as tk
import pyautogui
import pygetwindow as gw

def send_hotkey_to_last_active():
    # 1. Hide the GUI window immediately so it's not the "active" window
    root.withdraw()
    time.sleep(0.2)  # Give the OS a split second to register the window hiding
    
    try:
        # 2. Get all open windows
        all_windows = gw.getAllWindows()
        
        # 3. Filter for valid, visible windows with actual titles
        visible_windows = [w for w in all_windows if w.title and w.visible]
        
        if visible_windows:
            # The first visible window in the stack is now the last active one
            target_window = visible_windows[0]
            
            # 4. Force focus onto that window
            target_window.activate()
            time.sleep(0.9)  # Wait for focus animation to finish
            
            # 5. Send your hotkey (Change 'ctrl', 'n' to whatever you need!)
            pyautogui.hotkey('ctrl', 'n')
            print(f"Successfully triggered hotkey in: {target_window.title}")
            
    except Exception as e:
        print(f"Error targeting window: {e}")
        
    finally:
        # 6. Bring your button GUI back up on the screen
        root.deiconify()

# --- Create the GUI ---
root = tk.Tk()
root.title("Macro Trigger")
root.geometry("250x100")
# Keep the button window always on top of others for easy clicking
root.attributes('-topmost', True) 

# Add a simple, clean button
trigger_button = tk.Button(
    root, 
    text="⚡ Trigger Hotkey", 
    command=send_hotkey_to_last_active,
    font=("Arial", 12, "bold"),
    bg="#4CAF50",
    fg="white",
    padx=10,
    pady=10
)
trigger_button.pack(expand=True)

# Run the GUI loop
root.mainloop()
