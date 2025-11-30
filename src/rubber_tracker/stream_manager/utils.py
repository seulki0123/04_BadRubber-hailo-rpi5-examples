import time

import yaml

from rubber_tracker.utils.threading import CustomThread, load_config

class ActiveListener:
    def __init__(self, setting_file, active_controller):
        config = load_config()

        self.settings_file = setting_file
        self.active_controller = active_controller

        self.active = {}
        with open(self.settings_file, "r") as f:
            active_settings = yaml.safe_load(f)
        for zone, active in active_settings.items():
            self.active[zone] = active
            self.active_controller(zone, active)

        self._start_thread()
    
    def task(self):
        with open(self.settings_file, "r") as f:
            active = yaml.safe_load(f)

        for zone, active in active.items():
            if active != self.active[zone]:
                self.active_controller(zone, active)
                self.active[zone] = active

    def _start_thread(self):
        self.thread = CustomThread(name=self.__class__.__name__, task=self.task, interval=0.1)
        self.thread.start()