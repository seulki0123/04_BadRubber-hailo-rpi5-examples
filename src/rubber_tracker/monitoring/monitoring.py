from .resource_monitor import ResourceMonitor
from .voltage_monitor import VoltageMonitor
from rubber_tracker.utils import CustomThread

class Monitoring:
    def __init__(self):
        self.resource_monitor = ResourceMonitor()
        self.voltage_monitor = VoltageMonitor()

    def run(self):
        resource_thread = CustomThread(name=self.resource_monitor.__class__.__name__, task=self.resource_monitor.task, interval=self.resource_monitor.cpu_interval)
        voltage_thread = CustomThread(name=self.voltage_monitor.__class__.__name__, task=self.voltage_monitor.task, interval=self.voltage_monitor.logging_interval)
        resource_thread.start()
        voltage_thread.start()