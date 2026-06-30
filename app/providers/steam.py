"""Steam provider — friends online, rich presence."""

import logging
import pystray

log = logging.getLogger("iris.steam")


class SteamProvider:
    def __init__(self, cfg):
        self.cfg = cfg

    def start(self):
        pass  # TODO: Steam WebAPI / local files

    def menu_items(self):
        return []

    def poll_data(self):
        return {}
