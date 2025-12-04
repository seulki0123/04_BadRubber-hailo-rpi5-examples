# stream/services/external_id_service.py
from typing import Optional

from rubber_tracker.utils import ModuleLogger

class ExternalIdService(ModuleLogger):
    """
    Manages injection of external IDs and popping a valid ID for a zone using the provided queue manager and validator.
    Logs via provided logger functions to avoid depending on ModuleLogger here.
    """
    def __init__(self, queue_manager, validator, zone_map):
        super().__init__(self.__class__.__name__)
        self.queue = queue_manager
        self.validator = validator
        self.zone_map = zone_map
        
    def inject(self, data: dict) -> bool:
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

        data_to_store = self._build_data(data)
        if not self.queue.add_external_id(dst, data_to_store):
            return False

        self.log_info(f"External ID '{data_to_store['id']}(baler: {data_to_store['baler']})' added to zone '{dst}'")
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

    def queue_map(self, src_zone):
        """
        Map external source zone → internal queue zone.
        Example:
            config["gates"]["map"] = {"E1": "Z1", "E2": "Z2"}
        """
        return self.zone_map.get(src_zone)

    def _build_data(self, data):
        return {
            'id': data['id'],
            'baler': data['baler'],
            'time': data['time'],
        }
