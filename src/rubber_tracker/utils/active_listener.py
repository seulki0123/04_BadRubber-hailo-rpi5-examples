import time

import yaml

from .threading import CustomThread

class ActiveListener:
    def __init__(self, active_controller, config_path="config.yaml"):
        with open(config_path, "r") as f:
            default_active = yaml.safe_load(f)["gates"]["default_active"]

        self.log_path = "active.yaml"
        self.in1_active = default_active
        self.in2_active = default_active

        self.active_controller = active_controller
    
    def task(self):
        with open(self.log_path, "r") as f:
            active = yaml.safe_load(f)

        in1_active = active["in1"]
        in2_active = active["in2"]

        if in1_active != self.in1_active:
            self.active_controller("in1", in1_active)
            self.in1_active = in1_active

        if in2_active != self.in2_active:
            self.active_controller("in2", in2_active)
            self.in2_active = in2_active

    def start_thread(self):
        self.thread = CustomThread(name=self.__class__.__name__, task=self.task, interval=0.1)
        self.thread.start()