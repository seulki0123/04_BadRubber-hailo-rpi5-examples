from .queue import Queue
from ..utils.config_watcher import ConfigWatcher
from rubber_tracker.utils import ModuleLogger, load_config


class QueueManager(ModuleLogger):
    def __init__(self, config=None, zones=None):
        super().__init__(self.__class__.__name__)
        config = config or load_config().get("stream_queue", {})
        zones = zones or []

        self.queues = {z: Queue(z) for z in zones}
        self.global_ext_ids = set()

        active_file = config.get("active_file", "stream_active.yaml")
        self.active = {z: False for z in zones}
        self.config_watcher = ConfigWatcher(active_file, self.set_active)

    # ------------------------
    # Active control
    # ------------------------
    def set_active(self, zone, flag: bool):
        if zone not in self.active:
            self.log_error(f"Unknown zone: {zone}")
            return False
        self.active[zone] = flag
        self.log_info(f"Zone '{zone}' active={flag}")
        return True

    def is_active(self, zone):
        return self.active.get(zone, False)

    # ------------------------
    # External ID management
    # ------------------------
    def add_external_id(self, zone, data):
        ext_id = data.get('id')
        
        if not self.is_active(zone):
            self.log_info(f"Zone '{zone}' queue is not active, skipping external ID '{ext_id}'")
            return False

        if ext_id in self.global_ext_ids:
            self.log_warning(f"External ID '{ext_id}' already exists globally")
            return False

        q = self.queues.get(zone)
        if q is None:
            self.log_error(f"No queue for zone: {zone}")
            return False

        added = q.add(data)
        if not added:
            return False

        self.global_ext_ids.add(ext_id)
        self.log_info(f"Queue added. Lengths for zone '{zone}': {self.get_queue_lengths()[zone]}")
        return True

    def get_next_id(self, zone):
        q = self.queues.get(zone)
        if q is None:
            self.log_error(f"No queue for zone: {zone}")
            return None

        data = q.get()
        if data is None:
            return None

        self.log_info(f"Queue popped. Lengths for zone '{zone}': {self.get_queue_lengths()[zone]}")
        self.global_ext_ids.discard(data['id'])
        return data

    def get_queue_lengths(self):
        return {z: len(q) for z, q in self.queues.items()}

    def get_all_zones(self):
        return list(self.queues.keys())
