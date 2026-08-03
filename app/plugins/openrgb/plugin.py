"""OpenRGB plugin — thin orchestrator that delegates to the connector."""

from plugins.openrgb.connector import OpenRGBConnector


class Plugin:
    name = "openrgb"
    display_name = "OpenRGB"

    def __init__(self, cfg, serial_sender=None, overlays=None):
        self._cfg = cfg
        self._connector = OpenRGBConnector()
        self.overlays = overlays

    def start(self):
        self._connector.connect()

    def stop(self):
        self._connector.disconnect()

    def on_tap(self, control_id, value=None):
        self._connector.handle(control_id, value)

    def get_options(self, option_key):
        return self._connector.get_options(option_key)

    def poll(self):
        return {"available": self._connector.available}
