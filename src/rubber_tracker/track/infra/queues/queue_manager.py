from .queue import Queue
from ..utils.config_watcher import ConfigWatcher
from rubber_tracker.utils import ProcessLogger, load_config

class QueueManager(ProcessLogger):
    def __init__(self, config=None, zones=None):
        super().__init__(self.__class__.__name__)
        config = config or load_config().get("stream_queue", {})
        zones = zones or []

        self.queues = {z: Queue(z) for z in zones}
        self.global_ext_ids = set()  # external only

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
        self.log_info(f"External added. Lengths for zone '{zone}': {len(q)}")
        return True

    def push_left_trash(self, zone, data):
        if not self.is_active(zone):
            self.log_info(f"Zone '{zone}' inactive. Skip trash '{data['id']}'")
            return False

        q = self.queues.get(zone)
        if q is None:
            self.log_error(f"No queue for zone: {zone}")
            return False

        added = q.add_left(data)
        if not added:
            self.log_error(f"Failed to add trash to queue {zone}")
            return False

        self.log_info(f"Trash pushed-left. New length={len(q)} for zone '{zone}'")
        return True

    def get_next_id(self, zone):
        q = self.queues.get(zone)
        if q is None:
            self.log_error(f"No queue for zone: {zone}")
            return None

        data = q.get()
        if data is None:
            return None

        # external only
        if data['id'] in self.global_ext_ids:
            self.global_ext_ids.discard(data['id'])

        self.log_info(f"Queue popped. New length={len(q)}")
        return data

    def get_all_zones(self):
        return list(self.queues.keys())

    def clear_external_ids(self, zones):
        """
        Clear external IDs only for given zones.
        """
        removed = {}

        for zone in zones:
            q = self.queues.get(zone)
            if q is None:
                self.log_warning(f"No queue for zone: {zone}")
                continue

            removed_ids = q.clear()
            if removed_ids:
                removed[zone] = removed_ids

                # global_ext_ids 에서도 제거
                for eid in removed_ids:
                    self.global_ext_ids.discard(eid)

        self.log_info(f"External IDs cleared for zones {zones}: {removed}")
        return removed