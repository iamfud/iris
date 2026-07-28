"""PC Stats plugin — thin orchestrator that delegates to the connector."""

from plugins.pc_stats.connector import PCStatsConnector


class Plugin:
    name = "pc_stats"
    display_name = "PC Stats"

    def __init__(self, cfg, serial_sender=None):
        self._connector = PCStatsConnector(cfg, serial_sender)

    def start(self):
        self._connector.connect()

    def stop(self):
        pass

    def on_tap(self, control_id, value=None):
        self._connector.handle(control_id, value)

    def get_options(self, option_key):
        return self._connector.get_options(option_key)

    def poll(self):
        return {"available": self._connector.available}
