# Iris Plugin Developer Guide

Iris features a modular, featherweight plugin system. Third-party developers can create custom plugins to integrate simulators, games, smart home systems, or hardware peripherals directly into the Iris command centre.

---

## ⚡ Quickstart: Build a Plugin in 5 Minutes

Let's build a working telemetry plugin from scratch starting with an empty folder.

### 1. Open Your Plugins Folder
In Iris, open **Settings → General → Open Plugins** (or navigate to `%USERPROFILE%\Documents\Iris\plugins\`).

### 2. Create the Folder Structure
Create a new directory named `flight_tracker`:
```
Documents/Iris/plugins/
└── flight_tracker/
    ├── plugin.json         # Metadata & entity definitions
    └── plugin.py           # Python logic
```

### 3. Define the Manifest (`plugin.json`)
Create `plugin.json` inside `flight_tracker/`:
```json
{
  "name": "flight_tracker",
  "display_name": "Flight Tracker",
  "version": "1.0.0",
  "author": "Your Name",
  "description": "Exposes aircraft telemetry to Iris button decks and gauges.",
  "type": "service",
  "capabilities": {
    "status": true,
    "live_data": true
  },
  "live_data": {
    "fields": [
      {
        "key": "altitude",
        "label": "Altitude",
        "type": "number",
        "unit": "ft",
        "icon": "airplane-takeoff"
      },
      {
        "key": "airspeed",
        "label": "Airspeed",
        "type": "number",
        "unit": "kts",
        "icon": "speedometer"
      }
    ]
  }
}
```

### 4. Implement the Code (`plugin.py`)
Create `plugin.py` inside `flight_tracker/`:
```python
from iris_plugin import BasePlugin

class Plugin(BasePlugin):
    name = "flight_tracker"

    def __init__(self, cfg=None, *args, **kwargs):
        super().__init__(cfg, *args, **kwargs)
        self.altitude = 5000.0
        self.airspeed = 140.0

    def start(self):
        print("[flight_tracker] Plugin started")

    def stop(self):
        print("[flight_tracker] Plugin stopped")

    def poll(self):
        # In a real plugin, read values from SimConnect / REST API / serial port here
        return {
            "available": True,
            "altitude": self.altitude,
            "airspeed": self.airspeed
        }
```

### 5. Test It in Iris
1. Restart Iris (or reload the web panel).
2. Go to the **Generic Button Deck** editor on your Phone Panel or PC overlay.
3. Click any slot and select **Entity / Status**.
4. You will see `flight_tracker.altitude` and `flight_tracker.airspeed` available immediately with live values and gauges!

---

## 📁 Directory Anatomy

Plugins are discovered dynamically from the user plugins directory:
* **Installed Build**: `%USERPROFILE%\Documents\Iris\plugins\<plugin_name>\`
* **Portable Mode**: `<Iris Root>\plugins\<plugin_name>\`

Each plugin folder requires at minimum:
1. `plugin.json` — The declarative manifest declaring the plugin's metadata, target executable, settings controls, button definitions, and telemetry fields.
2. `plugin.py` — The Python entry point containing a class named `Plugin`.

---

## 📋 Manifest Specification (`plugin.json`)

The manifest defines how Iris displays, routes, and configures your plugin.

```json
{
  "name": "my_plugin",
  "display_name": "My Plugin Name",
  "version": "1.0.0",
  "author": "Developer Name",
  "description": "Short explanation of what this plugin does.",
  "type": "app",
  "exe_default": "TargetGame.exe",
  "message_not_running": "Waiting for TargetGame.exe to start...",
  "capabilities": {
    "status": true,
    "configuration": true,
    "buttons": true,
    "outputs": true,
    "live_data": true
  },
  "live_data": {
    "title": "Telemetry & Instruments",
    "fields": [
      {
        "key": "temperature",
        "label": "Engine Temp",
        "type": "number",
        "unit": "°C",
        "icon": "thermometer"
      }
    ]
  },
  "buttons": [
    {
      "id": "toggle_lights",
      "name": "Exterior Lights",
      "state_key": "lights_on",
      "icon": "lightbulb",
      "icon_off": "lightbulb-outline",
      "labels": { "on": "ON", "off": "OFF" },
      "default_hotkey": "Ctrl+Shift+L"
    }
  ],
  "outputs": [
    { "id": "display", "label": "Hardware Display", "enabled": true },
    { "id": "overlay", "label": "Desktop Overlay", "enabled": true }
  ],
  "settings": [
    {
      "title": "Connection Settings",
      "controls": [
        {
          "type": "text",
          "key": "server_ip",
          "label": "Server IP Address",
          "default": "127.0.0.1"
        },
        {
          "type": "slider",
          "key": "update_rate",
          "label": "Poll Rate",
          "min": 1,
          "max": 10,
          "default": 1,
          "unit": "s"
        }
      ]
    }
  ]
}
```

### Manifest Fields Reference

| Field | Type | Description |
| :--- | :--- | :--- |
| `name` | `string` | Unique internal identifier (e.g. `msfs_simconnect`, `openrgb`). Must match folder name. |
| `display_name` | `string` | Human-readable title shown in the UI. |
| `version` | `string` | Semantic version (e.g. `"1.0.0"`). |
| `type` | `string` | Lifecycle model: `"app"`, `"service"`, or `"multi"` (see below). |
| `exe_default` | `string` | Target executable name for `"app"` type (e.g. `"FlightSimulator.exe"`). |
| `capabilities` | `object` | Toggles which UI cards render on the Plugins page (`status`, `configuration`, `buttons`, `outputs`, `live_data`). |
| `live_data.fields`| `array` | List of telemetry sensors exposed to the Entity Bus. |
| `buttons` | `array` | In-game button deck and toggle controls. |
| `outputs` | `array` | Supported output destinations (`display`, `overlay`, `dashboard`). |
| `settings` | `array` | Declarative UI controls rendered in the Settings panel. |

---

## 🔄 Plugin Lifecycle & Types

Iris automatically manages your plugin's execution state with **zero idle CPU overhead**.

### Lifecycle Models (`"type"`)

1. **`"app"` (Process-Gated)**:
   - **Trigger**: Iris monitors Windows processes for `exe_default`.
   - **Behavior**: When the target game/application opens, Iris automatically calls `start()`. When the game exits, Iris calls `stop()` and suspends the plugin.
   - **Zero Idle Overhead**: While the game is closed, your plugin consumes 0 MB RAM and 0% CPU.

2. **`"service"` (Always-On)**:
   - **Trigger**: Starts automatically whenever Iris launches (if enabled).
   - **Behavior**: Suitable for local background services (OpenRGB, Home Assistant, REST servers).

3. **`"multi"` (Multi-Process)**:
   - **Trigger**: Starts only when **all** executables declared in `requirements` are running simultaneously (e.g. RTSS + MSI Afterburner).

---

## 🐍 Python Interface (`Plugin` Class)

You can inherit from `BasePlugin` (recommended) or create a standard duck-typed class:

```python
from iris_plugin import BasePlugin

class Plugin(BasePlugin):
    name = "my_plugin"

    def __init__(self, cfg=None, *args, **kwargs):
        super().__init__(cfg, *args, **kwargs)
        # Access persisted settings from self.config

    def start(self) -> None:
        """Called when plugin starts. Initialize connections/threads here."""
        pass

    def stop(self) -> None:
        """Called when plugin stops. Disconnect and cleanup here."""
        pass

    def poll(self) -> dict:
        """Polled every 1 second by Iris for telemetry and status.
        
        Return flat dictionary: {"available": True, "field_key": value}
        """
        return {"available": True}

    def on_button(self, button_id: str, slot_data: dict) -> bool:
        """Invoked when user taps a button on the companion deck or physical panel.
        
        Return True if handled; False to allow default hotkey fallback.
        """
        return True

    def on_action(self, action_id: str) -> bool:
        """Invoked when user clicks a momentary action button in settings."""
        return True
```

---

## 📊 Live Data & The Entity Bus

Any key returned from your `poll()` method that matches a field declared in `plugin.json` under `live_data.fields` is automatically registered on the **Iris Unified Entity Bus**.

### Example:
If your `plugin.json` defines:
```json
{
  "live_data": {
    "fields": [
      { "key": "hull_health", "label": "Hull Integrity", "type": "percentage" }
    ]
  }
}
```

And your `poll()` returns:
```python
def poll(self):
    return {
        "available": True,
        "hull_health": 85.5
    }
```

Iris will automatically:
1. Expose `my_plugin.hull_health` in the Button Deck configurator.
2. Render a dynamic circular gauge or status card on companion screens.
3. Stream live updates via WebSockets to connected phones/PWAs.

---

## 🔘 Button Controls & Actions

### In-Game Toggles & Deck Buttons
Declare buttons in `plugin.json`:
```json
{
  "buttons": [
    {
      "id": "landing_gear",
      "name": "Landing Gear",
      "state_key": "gear_down",
      "icon": "airplane-landing",
      "icon_off": "airplane-takeoff",
      "labels": { "on": "DOWN", "off": "UP" },
      "default_hotkey": "G"
    }
  ]
}
```

When a user taps the tile on their phone:
1. Iris calls `inst.on_button("landing_gear", slot_data)`.
2. If `on_button` returns `True`, Iris considers the action handled.
3. If `on_button` returns `False` (or is not implemented), Iris automatically injects the `default_hotkey` (`"G"`) using its native keyboard service.

---

## ⚙️ Declarative Settings UI

Iris dynamically builds the Settings UI for your plugin from `plugin.json`. You never need to write HTML, CSS, or JavaScript.

### Supported Control Types

| Control Type | Manifest Definition |
| :--- | :--- |
| **Toggle** | `{"type": "toggle", "key": "auto_connect", "label": "Auto-Connect"}` |
| **Text Input** | `{"type": "text", "key": "api_key", "label": "API Key", "placeholder": "Enter token"}` |
| **Slider** | `{"type": "slider", "key": "volume", "label": "Volume", "min": 0, "max": 100, "unit": "%"}` |
| **Select / Dropdown** | `{"type": "select", "key": "profile", "label": "Profile", "options_key": "my_profiles"}` |

Access saved values anytime inside your Python code via:
```python
api_key = self.config.get("api_key", "default_value")
```

---

## 📦 Publishing & Distributing Plugins

To share your plugin with other Iris users:
1. Zip your plugin folder:
   ```
   my_plugin.zip
   └── my_plugin/
       ├── plugin.json
       └── plugin.py
   ```
2. Users can simply extract the folder into their `%USERPROFILE%\Documents\Iris\plugins\` directory.
3. On next launch (or upon clicking "Reload Plugins" in Settings), Iris instantly discovers and loads the plugin!
