# Iris — PC Companion Overlay

A Windows desktop companion that displays PC stats (CPU/GPU temps, clock, notifications) and controls Home Assistant entities via an ESP8266/ESP32-driven secondary display. The main panel is an iPhone-shaped floating overlay with gauges, quick tiles, and Home Assistant shortcuts.

## Hardware Required

- **ESP8266 (Wemos D1 Mini) or ESP32** running the firmware in `firmware/d1mini/`
- **IPS LCD display** (128×128 or similar, ST7735/ST7789) connected to the ESP over SPI
- **USB cable** to connect the ESP to your PC

The ESP connects over USB serial, receives stats/commands from the PC, and drives the secondary display. Optional: relays/IR LEDs for physical button backlight control.

## Features

- **Live PC stats** — CPU/GPU temperature, usage, FPS
- **Large clock** with date, minute bar, and ambient "eyes" animation
- **Notification mirroring** — Windows notifications pushed to the display
- **Home Assistant integration** — View sensor states, trigger shortcuts
- **Alarm clock** — Set alarms from the PC, dismiss/snooze from the panel
- **Media controls** — Now-playing display via Windows SMTC
- **Audio visualizer** — FFT-based spectrum on the secondary display
- **OpenRGB integration** — Sync RGB profiles
- **Steam integration** — Friends online / game status
- **Global hotkey** — `Ctrl+Alt+I` to toggle the overlay

## Dependencies

- Python 3.10+
- Windows 10/11
- See `requirements.txt` for full list

## Quick Start

### 1. Flash the firmware

Open `firmware/d1mini/main/main.ino` in the Arduino IDE, select your ESP board, and upload.

### 2. Install the Python app

```bash
pip install -r requirements.txt
python app/main.py
```

The app runs in the system tray. Click the tray icon or press `Ctrl+Alt+I` to show the overlay panel.

### 3. Build a standalone executable (optional)

```bash
build.bat
```

Output: `dist/Iris.exe`

## Configuration

Configuration is stored in `%APPDATA%/Iris/iris_config.json` (installed) or `app/iris_config.json` (source). Edit via the Settings dialog or directly.

Key settings:
- `serial_port` — COM port for the ESP (`"auto"` for automatic detection)
- `ha_url` / `ha_token` — Home Assistant connection
- `brightness` — Display brightness (0–5)
- `alarms` — JSON array of alarm schedules

## Project Structure

```
Iris/
├── app/                    # Python desktop application
│   ├── main.py             # Entry point
│   ├── main_window.py      # iPhone-shaped overlay window
│   ├── settings_dialog.py  # Settings UI
│   ├── overlay_window.py   # Numline-style overlay
│   ├── serial_comm.py      # USB serial bridge to ESP
│   ├── win_platform.py     # Windows-specific helpers
│   ├── providers/          # Data providers (Stats, HA, Media, etc.)
│   ├── config.py           # JSON config management
│   └── constants.py        # Design tokens, defaults
├── firmware/
│   └── d1mini/main/        # ESP8266/32 Arduino firmware
├── requirements.txt
└── build.bat
```

## License

MIT
