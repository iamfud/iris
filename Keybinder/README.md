# Iris Keybinder (Standalone Test Platform)

This directory is an **isolated standalone test platform** for hardware keystroke and shortcut injection. It is completely decoupled from the main Iris project so you can safely test game bindings at your own pace.

---

## Safety Features

1. **Guaranteed Key Release**: Every keypress uses a `try ... finally` block so that the key-up event is guaranteed to fire, even on error or interruption.
2. **Emergency Key Release**: If any key is ever stuck, run:
   ```bash
   python emergency_release.py
   ```
3. **Smart Character Mapping**: Entering `"1"` maps to Scancode `0x02` (Key 1), never `Escape`.

---

## How to Test Manually

Open PowerShell or Command Prompt in this folder (`D:\Iris\iris_3_0\Keybinder\`):

### 1. Interactive Test Menu
```bash
python test_keyboard_input.py
```

### 2. Direct Key Testing (3-Second Countdown)
```bash
# Test single keys
python test_keyboard_input.py 1
python test_keyboard_input.py 2
python test_keyboard_input.py f13
python test_keyboard_input.py space

# Test key combinations
python test_keyboard_input.py ctrl+1
python test_keyboard_input.py ctrl+shift+k
python test_keyboard_input.py alt+j
```

### 3. Check Driver Status
```bash
python test_keyboard_input.py --check
```

### 4. Emergency Reset
```bash
python emergency_release.py
# or
python test_keyboard_input.py --release-all
```
