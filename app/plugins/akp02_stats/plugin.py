"""AKP02 PC Stats Display Plugin for Iris.

Renders pcstats_dashboard.html via headless Edge CDP and streams frames to
the physical AKP02 USB display panel.
"""

import logging
import os
import threading
import time
from typing import Any, Dict, Optional

try:
    from iris_plugin import BasePlugin
except ImportError:
    import sys
    app_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if app_dir not in sys.path:
        sys.path.insert(0, app_dir)
    from iris_plugin import BasePlugin

try:
    from .cdp import HeadlessRenderer
except Exception:
    import importlib.util
    cdp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cdp.py")
    spec = importlib.util.spec_from_file_location("akp02_stats_cdp", cdp_path)
    cdp_mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cdp_mod)
    HeadlessRenderer = cdp_mod.HeadlessRenderer

log = logging.getLogger("iris.plugins.akp02_stats")

try:
    from displays.registry import get_driver
except ImportError:
    get_driver = None

DASH_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pcstats_dashboard.html")


class Plugin(BasePlugin):
    name = "akp02_stats"
    display_name = "AKP02 PC Stats Display"

    def __init__(self, cfg: Optional[Dict[str, Any]] = None, *args: Any, **kwargs: Any) -> None:
        super().__init__(cfg, *args, **kwargs)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._panel = None
        self._renderer: Optional[HeadlessRenderer] = None
        self._panel_connected = False
        self._browser_connected = False
        self._current_fps = 0.0

    def start(self) -> None:
        """Start the background AKP02 render thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._render_loop, daemon=True, name="akp02-stats-render")
        self._thread.start()
        log.info("[akp02_stats] Plugin started")

    def stop(self) -> None:
        """Stop rendering, terminate headless browser, and disconnect panel."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._teardown_renderer()
        self._teardown_panel()
        self._panel_connected = False
        self._browser_connected = False
        self._current_fps = 0.0
        log.info("[akp02_stats] Plugin stopped")

    def poll(self) -> Dict[str, Any]:
        """Expose live state to Iris entity bus."""
        driver = get_driver("akp02") if get_driver else None
        panel_conn = (driver.is_connected if driver else False)
        return {
            "available": panel_conn,
            "panel_connected": panel_conn,
            "browser_connected": self._browser_connected,
            "render_fps": round(self._current_fps, 1),
            "brightness": driver.get_brightness() if driver else getattr(self, "_current_brightness", 80),
        }

    def set_brightness(self, value: int) -> bool:
        """Dynamically set hardware backlight brightness (0-100%)."""
        val = max(0, min(100, int(value)))
        self.config["brightness"] = val
        self._current_brightness = val
        driver = get_driver("akp02") if get_driver else None
        if driver:
            applied = driver.set_brightness(val)
            if applied:
                log.info("[akp02_stats] hardware brightness set to %d%% via driver", val)
                return True
        return False

    def on_action(self, action_id: str, value: Any = None) -> bool:
        if action_id in ("set_brightness", "brightness"):
            if value is not None:
                return self.set_brightness(int(value))
        return False

    def _teardown_renderer(self):
        if self._renderer:
            try:
                self._renderer.close()
            except Exception as ex:
                log.debug("[akp02_stats] Renderer close error: %s", ex)
            self._renderer = None
        self._browser_connected = False

    def _teardown_panel(self):
        self._panel_connected = False

    def _get_telemetry_snapshot(self) -> Dict[str, Any]:
        """Fetch latest telemetry snapshot from Iris TelemetryEngine or fallback."""
        try:
            from telemetry import get_telemetry_engine
            return get_telemetry_engine().get_snapshot()
        except Exception:
            pass

        import psutil
        vm = psutil.virtual_memory()
        return {
            "cpu": psutil.cpu_percent(interval=None),
            "ram_pct": vm.percent,
            "ram_used": round(vm.used / 1e9, 1),
            "ram_total": round(vm.total / 1e9, 1),
        }

    def _get_latest_config(self) -> Dict[str, Any]:
        """Fetch latest config from disk when modified, caching in self._cfg."""
        now = time.time()
        if now - getattr(self, "_last_cfg_check", 0) > 0.5:
            self._last_cfg_check = now
            try:
                from config import config_path, load_config
                c_path = config_path()
                if os.path.isfile(c_path):
                    mtime = os.path.getmtime(c_path)
                    if mtime != getattr(self, "_last_cfg_mtime", None):
                        self._last_cfg_mtime = mtime
                        self._cfg = load_config()
            except Exception:
                pass
        return self._cfg or {}

    def on_theme(self, theme_data: Dict[str, Any]) -> None:
        """Invoked when global theme changes (via macros, game latching, or settings)."""
        if isinstance(theme_data, dict):
            self._macro_theme = dict(theme_data)

    def _resolve_accent_color(self) -> str:
        """Resolve current accent color based on active Iris theme mode and macros."""
        # 1. Plugin-specific user override in plugin settings (if set)
        pcfg = self.config
        plugin_accent = (pcfg.get("accent_color") or "").strip()
        if plugin_accent:
            return plugin_accent

        # 2. Macro-specified or latched global theme (takes top priority if active)
        theme = getattr(self, "_macro_theme", None)

        # 3. In-memory runtime theme from plugin_manager
        if not theme:
            try:
                import plugin_manager
                theme = (plugin_manager._cfg or {}).get("theme")
            except Exception:
                pass

        # 4. Fallback to latest persisted config
        if not theme:
            cfg = self._get_latest_config()
            theme = cfg.get("theme") or {}

        if not isinstance(theme, dict):
            return "#48B2E9"

        mode = theme.get("mode") or "iris"
        if mode == "monochrome":
            return "#FFFFFF"
        if mode == "iris":
            return "#48B2E9"
        if mode == "custom":
            return theme.get("custom_neon") or theme.get("neon") or "#48B2E9"

        return theme.get("neon") or "#48B2E9"

    def _render_loop(self):
        """Worker thread orchestrating headless CDP updates and transmitting to AKP02 driver."""
        while self._running:
            pcfg = self.config
            enabled = pcfg.get("enabled", True)
            if not enabled:
                self._teardown_renderer()
                self._teardown_panel()
                time.sleep(1.0)
                continue

            driver = get_driver("akp02") if get_driver else None
            if not driver:
                log.debug("[akp02_stats] AKP02 display driver not registered. Waiting...")
                time.sleep(3.0)
                continue

            # Check for live brightness adjustments
            target_brightness = int(pcfg.get("brightness", 85))
            if target_brightness != getattr(self, "_current_brightness", None):
                self._current_brightness = target_brightness
                try:
                    driver.set_brightness(target_brightness)
                except Exception:
                    pass

            # 1. Launch headless browser CDP renderer if not active
            if not self._renderer or not self._renderer.is_alive:
                try:
                    log.info("[akp02_stats] Launching headless browser for %s", DASH_HTML)
                    self._renderer = HeadlessRenderer(DASH_HTML)
                    self._browser_connected = True
                    time.sleep(0.8)  # Let initial DOM load and paint
                except Exception as b_err:
                    log.error("[akp02_stats] Headless browser launch failed: %s", b_err)
                    self._browser_connected = False
                    self._teardown_renderer()
                    time.sleep(4.0)
                    continue

            # 2. Render frame loop
            fps_target = float(pcfg.get("target_fps", 4.0))
            frame_delay = 1.0 / max(0.5, min(fps_target, 30.0))
            accent_to_use = self._resolve_accent_color()

            frame_start = time.time()
            try:
                stats = self._get_telemetry_snapshot()
                if accent_to_use:
                    stats["accent"] = accent_to_use

                self._renderer.update(stats)
                frame_img = self._renderer.capture()
                ok = driver.show(frame_img)
                self._panel_connected = ok

                elapsed = time.time() - frame_start
                self._current_fps = 1.0 / max(0.001, elapsed)

                sleep_time = max(0.0, frame_delay - elapsed)
                time.sleep(sleep_time)

            except Exception as frame_err:
                log.warning("[akp02_stats] Render frame error: %s", frame_err)
                err_str = str(frame_err).lower()
                if "closed" in err_str or "10054" in err_str or "broken" in err_str or "timeout" in err_str:
                    # Broken pipe or closed browser
                    self._teardown_renderer()
                    self._teardown_panel()
                    time.sleep(2.0)
                else:
                    time.sleep(0.5)
