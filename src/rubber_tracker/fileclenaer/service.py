import os

from rubber_tracker.utils import CustomThread, load_config

from .base_cleaner import BaseFileCleaner

class FileCleaner(BaseFileCleaner):
    def __init__(self, config, cleaner_name: str):
        super().__init__(
            name=cleaner_name,
            root=os.getcwd(),
            cleaner_cfg=config[cleaner_name],
        )


class FileCleanerService:
    def __init__(self):
        cleaner_cfg = load_config()["cleaner"]

        self.cleaners = [
            FileCleaner(cleaner_cfg, name)
            for name, cfg in cleaner_cfg.items()
            if cfg.get("enabled", False)
        ]

    def run(self):
        for cleaner in self.cleaners:
            CustomThread(
                name=cleaner.name,
                task=cleaner.task,
                interval=cleaner.thread_interval,
            ).start()