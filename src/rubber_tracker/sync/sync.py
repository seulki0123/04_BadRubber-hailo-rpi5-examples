from datetime import datetime

from rubber_tracker.utils import ModuleLogger, load_config
from .base import BaseSyncModel

class SyncManager(ModuleLogger):
    def __init__(self):
        super().__init__(self.__class__.__name__)
        config = load_config()
        time_sync_enabled = config["sync"]["time"]["enabled"]
        time_max_queue_size = config["sync"]["time"]["max_queue_size"]
        time_valid_queue_size = config["sync"]["time"]["valid_queue_size"]
        time_tolerance = config["sync"]["time"]["tolerance"]

        bale_sync_enabled = config["sync"]["bale"]["enabled"]
        bale_max_queue_size = config["sync"]["bale"]["max_queue_size"]
        bale_valid_queue_size = config["sync"]["bale"]["valid_queue_size"]
        bale_tolerance = config["sync"]["bale"]["tolerance"]

        self.time_external_zone = config["sync"]["time"]["external_zone"]
        self.time_internal_zone = config["sync"]["time"]["internal_zone"]
        self.bale_external_zone = config["sync"]["bale"]["external_zone"]
        self.bale_internal_zone = config["sync"]["bale"]["internal_zone"]
        
        self.time_sync = BaseSyncModel("time", time_max_queue_size, time_valid_queue_size, time_tolerance) if time_sync_enabled else None
        self.bale_sync = BaseSyncModel("bale", bale_max_queue_size, bale_valid_queue_size, bale_tolerance) if bale_sync_enabled else None

    def add_external_time(self, data):
        time = data.get("time")
        zone = data.get("zone")
        if zone != self.time_external_zone:
            return

        if time:
            self.time_sync.add_external(self._parse_time(time))
        else:
            self.log_error("Time data is missing")

    def add_internal_time(self, data):
        time = data.get("time")
        zone = data.get("zone")
        if zone != self.time_internal_zone:
            return
            
        if time:
            self.time_sync.add_internal(self._parse_time(time))
            self.time_sync.sync(mode="diff")
        else:
            self.log_error("Time data is missing")


    def add_external_bale(self, data):
        baler = data.get("baler")
        zone = data.get("zone")
        if zone != self.bale_external_zone:
            return

        if baler:
            self.bale_sync.add_external(baler)
        else:
            self.log_error("Bale data is missing")

    def add_internal_bale(self, data):
        baler = data.get("baler")
        zone = data.get("zone")
        if zone != self.bale_internal_zone:
            return

        if baler:
            self.bale_sync.add_internal(baler)
            self.bale_sync.sync(mode="strict")
        else:
            self.log_error("Bale data is missing")

    def _parse_time(self, time_str: str):
        try:
            if "." in time_str:
                return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
            else:
                return datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except ValueError as e:
            self.log_error(f"Invalid time format: {time_str} ({e})")
            return None