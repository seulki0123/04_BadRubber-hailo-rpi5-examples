from .resource_monitor import ResourceMonitor
from .voltage_monitor import VoltageMonitor
from .log_cleaner import LogCleaner
from rubber_tracker.utils import CustomThread

class Monitoring:
    def __init__(self):
        self.resource_monitor = ResourceMonitor()
        self.voltage_monitor = VoltageMonitor()
        # 로그 보관 기간이 지난 파일을 주기적으로 삭제 (기본 30일, config 로 조정)
        self.log_cleaner = LogCleaner()

    def run(self):
        resource_thread = CustomThread(name=self.resource_monitor.__class__.__name__, task=self.resource_monitor.task, interval=self.resource_monitor.cpu_interval)
        voltage_thread = CustomThread(name=self.voltage_monitor.__class__.__name__, task=self.voltage_monitor.task, interval=self.voltage_monitor.logging_interval)
        # interval 은 LogCleaner 자체가 config 에서 읽은 값(thread_interval)을 사용
        log_cleaner_thread = CustomThread(
            name=self.log_cleaner.__class__.__name__,
            task=self.log_cleaner.task,
            interval=self.log_cleaner.thread_interval,
        )
        resource_thread.start()
        voltage_thread.start()
        log_cleaner_thread.start()