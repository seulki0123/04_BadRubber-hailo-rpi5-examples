from .queue import Queue
from rubber_tracker.utils import ModuleLogger


class QueueManager(ModuleLogger):
    def __init__(self, zones=None):
        super().__init__(self.__class__.__name__)
        zones = zones or []

        self.queues = {z: Queue(z) for z in zones}
        self.global_ext_ids = set()

    def add_external_id(self, zone, ext_id, baler):
        if ext_id in self.global_ext_ids:
            self.log_warning(f"External ID '{ext_id}' already exists globally")
            return False

        q = self.queues.get(zone)
        if q is None:
            self.log_error(f"No queue for zone: {zone}")
            return False

        added = q.add((ext_id, baler))
        if not added:
            return False

        self.global_ext_ids.add(ext_id)
        return True

    def get_next_id(self, zone):
        q = self.queues.get(zone)
        if q is None:
            self.log_error(f"No queue for zone: {zone}")
            return None

        data = q.get()
        if data is None:
            return None

        ext_id, baler = data
        self.global_ext_ids.discard(ext_id)
        return data

    def add_zone(self, zone):
        if zone in self.queues:
            return False
        self.queues[zone] = Queue(zone)
        return True

    def get_queue_lengths(self):
        return {z: len(q) for z, q in self.queues.items()}

    def get_all_zones(self):
        return list(self.queues.keys())
