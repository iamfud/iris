# Iris — Dynamic PC Command Centre

[![Download Windows Installer](https://img.shields.io/badge/Download-Windows%20Installer-00ff88?style=for-the-badge&logo=windows&logoColor=black)](https://e.pcloud.link/publink/show?code=XZ5Wg77ZETccmrFfhx7pDqtnauRWtLck45dk)
[![Setup Guide](https://img.shields.io/badge/Setup%20Guide-iamfud.github.io%2Firis-48B2E9?style=for-the-badge)](https://iamfud.github.io/iris/)

A dynamic, context-aware control and automation utility that turns your PC into a command centre. Iris continuously detects which game or application is in focus and **automatically tags and organizes every screenshot, quick note, color sample, and OCR text clip under that specific title** — zero folder sorting, zero file dialogs, and no Alt-Tabbing required.

Control and automate **lighting**, summon an ultra-fast **in-game notepad**, run a **screen-capture toolbar with annotations and OCR**, mix **media and per-app volumes**, monitor **PC statistics** (FPS live from RTSS), run an **alarm, stopwatch, and countdown timer**, and drive custom **button boxes** in games, simulators, and apps. A **conditional macro system** with hotkey injection and reactive events ties it together — for example, switch lighting or inject commands on game state changes.

Everything you capture, OCR, and note is collected into an **integrated library browser**, and the whole thing is extended by **plugins and addons including Home Assistant**. Iris can also drive an optional ESP8266/ESP32 + MAX7219 LED matrix display, a floating overlay, and a phone/PWA panel.

> 📦 **Download Windows Installer:** [Iris_Setup.exe (pCloud)](https://e.pcloud.link/publink/show?code=XZ5Wg77ZETccmrFfhx7pDqtnauRWtLck45dk)  
> 📖 **Full step-by-step setup guide:** https://iamfud.github.io/iris/

## Hardware Required (optional — for the LED display)

- **ESP8266 (Wemos D1 Mini) or ESP32** running the firmware in `firmware/d1mini/`
- **MAX7219 LED matrix display** (or daisy-chained modules) driven by the ESP over SPI
- **USB cable** to connect the ESP to your PC

The ESP connects over USB serial, receives stats/commands from the PC, and drives the MAX7219 display. The capture, mixing, macro, and control features all work *without* the display.

### Wiring (ESP8266 D1 Mini → MAX7219)

| MAX7219 | D1 Mini |
|---------|---------|
| VCC     | 5V      |
| GND     | GND     |
| DIN     | D7 (GPIO13) |
| CLK     | D5 (GPIO14) |
| CS      | D2 (GPIO4)  |

Display type: `FC16_HW` — 4 daisy-chained 8×8 LED matrix modules.

## Features

- **Automatic app-linked organization** — every note, screenshot, OCR clip, and color sample is automatically tagged and filed by the active game or application in focus
- **Foreground-locked Iris Note** — summon a persistent floating notepad directly over 3D games with immediate typing focus and zero lag; automatically bound to the active session
- **Capture toolbar + annotations** — fullscreen/zone screenshots with pixel annotations and automatic app filing
- **OCR on every capture** — every capture is OCR'd to your clipboard and stored in your app library
- **Capture text to clipboard** — standalone OCR that grabs text from any screen region, no screenshot needed
- **Color picker** — system-wide pixel colour grab with HEX/RGB to clipboard
- **Media mixing & app volume** — full transport controls plus per-application volume/mute
- **Live PC stats** — CPU/GPU temperature (MSI Afterburner) and FPS, read live from RTSS
- **Alarm, stopwatch & countdown** — alarms from your PC, plus an on-screen stopwatch and countdown timer
- **Game / app button boxes** — custom button-box overlays in simulators, games, and apps
- **Vision system** — screen sensors firing events on colour conditions (colour % / pixel match / brightness)
- **Conditional macros & hotkeys** — reactive events with hotkey injection (e.g. lighting changes on state events)
- **Home Assistant & plugins** — extensible addons/plugins for smart home, lighting, simulators, and telemetry
- **Phone / PWA panel** — pair and control from your phone
- **Optional MAX7219 display** — clock, notification mirroring, stats on a physical LED matrix
- **Global hotkey** — `Ctrl+Alt+I` to toggle the overlay

## Dependencies

- Python 3.10+
- Windows 10/11
- See `requirements.txt` for full list

## Quick Start

### 1. Download & Install (Recommended)

Download and run the Windows installer:
👉 **[Download Iris_Setup.exe](https://e.pcloud.link/publink/show?code=XZ5Wg77ZETccmrFfhx7pDqtnauRWtLck45dk)**

The installer automatically configures:
- Iris desktop application and startup shortcuts
- Built-in plugins for simulators, smart home, lighting, PC stats, and vision
- Visual C++ 2015–2022 and Edge WebView2 runtime dependencies
- Low-latency keyboard interception driver

### 2. Flash the firmware (optional — for the LED display)

Open `firmware/d1mini/main/main.ino` in the Arduino IDE, select your ESP board, and upload.

### 3. Or run from Python source (Developers)

```bash
pip install -r requirements.txt
python app/main.py
```

The app runs in the system tray. Click the tray icon or press `Ctrl+Alt+I` to show the overlay panel.

### 4. Build a standalone executable (optional)

```bash
build.bat
```

Output: `dist/Iris.exe` and `Installer/Iris_Setup.exe`

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
│   ├── capture_toolbar.py  # Screen-capture toolbar with annotations & OCR
│   ├── colour_picker.py    # System-wide colour picker
│   ├── notepad_window.py   # Built-in notepad
│   ├── quick_note.py       # Quick notes
│   ├── win_volume.py       # Per-application volume mixing & mute
│   ├── lighting_service.py # Generic lighting / profile-focus manager
│   ├── keyboard_service.py # Hotkey injection backend
│   ├── automations.py      # Conditional macro & reactive-event engine
│   ├── vision.py           # Screen-analysis engine + OCR primitives
│   ├── alarm_popup.py      # Alarm popup (dismiss/snooze from the panel)
│   ├── alarm_sound.py      # Alarm sound playback
│   ├── stopwatch.py        # Floating stopwatch / countdown-timer overlay
│   ├── serial_comm.py      # USB serial bridge to ESP (optional display)
│   ├── win_platform.py     # Windows-specific helpers
│   ├── providers/          # Data providers (Stats, HA, Media, etc.)
│   ├── plugins/            # Plugin system & bundled plugins
│   ├── config.py           # JSON config management
│   └── constants.py        # Design tokens, defaults
├── firmware/
│   └── d1mini/main/        # ESP8266/32 Arduino firmware
├── docs/                   # GitHub Pages documentation site
├── requirements.txt
└── build.bat
```

## License

MIT
