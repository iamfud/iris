"""Data source providers for Iris.

Each provider is a class with:
- start() — begin background polling
- stop() — clean shutdown
- menu_items() — return list of pystray MenuItem for the tray menu
- poll_data() — return dict of current state for the dashboard
"""


class BaseProvider:
    def start(self):
        pass

    def stop(self):
        pass

    def menu_items(self):
        return []

    def poll_data(self):
        return {}
