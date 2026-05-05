"""
FileCleanerService — fileclenaer 모듈의 thread 기동/관리 진입점.

LogCleaner / CaptureCleaner / RecordingCleaner 인스턴스를 만들고, 각자
자신의 thread_interval (config 로 읽어둠) 로 CustomThread 를 띄운다.
"""

from rubber_tracker.utils import CustomThread

from .capture_cleaner import CaptureCleaner
from .log_cleaner import LogCleaner
from .rec_cleaner import RecordingCleaner


class FileCleanerService:
    """파일 정리 서비스 묶음.

    Monitoring 클래스가 ResourceMonitor / VoltageMonitor 를 묶듯, 본 서비스는
    LogCleaner / CaptureCleaner / RecordingCleaner 를 묶어 각각의 주기 thread
    를 띄운다. interval 은 각 cleaner 자체가 config 에서 읽은 값
    (thread_interval)을 사용.
    """

    def __init__(self):
        self.log_cleaner = LogCleaner()
        self.capture_cleaner = CaptureCleaner()
        self.recording_cleaner = RecordingCleaner()

    def run(self):
        cleaners = [
            self.log_cleaner,
            self.capture_cleaner,
            self.recording_cleaner,
        ]
        for cleaner in cleaners:
            CustomThread(
                name=cleaner.__class__.__name__,
                task=cleaner.task,
                interval=cleaner.thread_interval,
            ).start()
