from .resource_monitor import ResourceMonitor
from .voltage_monitor import VoltageMonitor
from rubber_tracker.utils import CustomThread


class Monitoring:
    """리소스/전압 등 시스템 지표 모니터링 thread 묶음.

    파일 정리 (LogCleaner / CaptureCleaner) 는 rubber_tracker.fileclenaer
    의 FileCleanerService 가 담당하므로 여기서는 다루지 않는다.
    """

    def __init__(self):
        self.resource_monitor = ResourceMonitor()
        self.voltage_monitor = VoltageMonitor()

    def run(self):
        resource_thread = CustomThread(
            name=self.resource_monitor.__class__.__name__,
            task=self.resource_monitor.task,
            interval=self.resource_monitor.cpu_interval,
        )
        voltage_thread = CustomThread(
            name=self.voltage_monitor.__class__.__name__,
            task=self.voltage_monitor.task,
            interval=self.voltage_monitor.logging_interval,
        )
        resource_thread.start()
        voltage_thread.start()
