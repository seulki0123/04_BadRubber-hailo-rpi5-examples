from typing import Optional
from datetime import datetime

from rubber_tracker.utils import ProcessLogger

class ExternalIdService(ProcessLogger):
    """
    Manages injection of external IDs and popping a valid ID for a zone using the provided queue manager and validator.
    Logs via provided logger functions to avoid depending on ProcessLogger here.
    """
    def __init__(self, queue_manager, validator, zone_map, fallback_service, unsynced_baler):
        super().__init__(self.__class__.__name__)
        self.queue = queue_manager
        self.validator = validator
        self.zone_map = zone_map
        self.fallback_service = fallback_service
        self.unsynced_baler = unsynced_baler

    def inject(self, data: dict, synced_zones: list) -> bool:
        required = {"id", "baler", "zone", "time"}
        missing = required - data.keys()
        if missing:
            self.log_error(f"Missing fields: {missing} in data {data}")
            return False

        src = data.get("zone")
        dst = self.queue_map(src)
        if dst is None:
            self.log_error(f"From zone '{src}' not mapped to any queue")
            return False

        if dst not in self.queue.get_all_zones():
            self.log_error(f"Target zone '{dst}' not found in queues")
            return False

        self.log_info(f"Synced zones: {synced_zones}, dst: {dst} in synced_zones: {dst in synced_zones}")
        data_to_store = self._build_data(data, dst in synced_zones)
        if not self.queue.add_external_id(dst, data_to_store):
            return False

        self.log_info(f"External ID '{data_to_store['id']}(input_baler: {data_to_store['input_baler']})' added to zone '{dst}'")
        self._dump_all_ids()
        return True

    def pop_valid(self, zone) -> Optional[dict]:
        """
        Pop next id for zone if valid according to validator.
        Returns None if queue empty or fallback required.
        """
        while True:
            data = self.queue.get_next_id(zone)
            if data is None:
                return None

            valid, delete = self.validator.validate(data["time"], zone)
            if valid:
                return data

            if not delete:
                # early -> return None so caller triggers fallback if desired
                return None

            # delete==True && not valid -> it was expired, continue to next
            self.log_error(f"External ID '{data['id']}' deleted from zone '{zone}' (time exceeded)")

    def push_left_trash(self, zone, count=1):
        for _ in range(count):
            trash_id = self.fallback_service.get_fallback_id(1)
            trash_data = {
                "id": trash_id,
                "input_baler": self.unsynced_baler,
                "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            }

            ok = self.queue.push_left_trash(zone, trash_data)
            if not ok:
                return False

        return True
        
    def queue_map(self, src_zone):
        """
        Map external source zone → internal queue zone.
        Example:
            config["gates"]["map"] = {"E1": "Z1", "E2": "Z2"}
        """
        return self.zone_map.get(src_zone)

    def _build_data(self, data, synced: bool):
        return {
            'id': data['id'],
            'input_baler': int(data['baler']) if data['baler'] is not None else None,
            'time': data['time'],
            'synced': synced,
        }

    def _dump_all_ids(self):
        result = {}

        for zone, queue in self.queue.queues.items():
            ids = [item['id'] for item in list(queue._ext_ids)]
            result[zone] = ids

        # 로그 출력
        for zone, ids in result.items():
            self.log_info(f"{zone}: {ids}")

        return result