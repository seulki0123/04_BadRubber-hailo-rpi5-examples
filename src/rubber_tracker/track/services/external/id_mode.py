from collections import defaultdict
from enum import Enum
from threading import RLock

from rubber_tracker.utils import ProcessLogger


class SyncMode(str, Enum):
    VALID = "VALID"
    FIFO = "FIFO"


class IDModeManager(ProcessLogger):

    def __init__(self, initial_mode=SyncMode.VALID):
        super().__init__(self.__class__.__name__)

        self._lock = RLock()

        # zone -> ingest mode
        self._ingest_mode = defaultdict(
            lambda: initial_mode
        )

        # zone -> {ext_id: mode}
        self._id_modes = defaultdict(dict)

    # -------------------------
    # ID lifecycle operations
    # -------------------------
    def register(self, zone, ext_id):
        with self._lock:
            mode = self._ingest_mode[zone]
            self._id_modes[zone][ext_id] = mode
        self.log_info(f"Registered ID '{ext_id}' as mode={mode} in zone='{zone}'")

    def pop_id_mode(self, zone, ext_id):
        with self._lock:
            return self._id_modes[zone].pop(ext_id)

    def put_back(self, zone, ext_id, mode):
        with self._lock:
            self._id_modes[zone][ext_id] = mode

    # -------------------------
    # mode control
    # -------------------------
    def set_mode(self, zone, mode):
        updated_ids = []

        with self._lock:
            old = self._ingest_mode[zone]
            self._ingest_mode[zone] = mode

            if mode == SyncMode.FIFO:
                for ext_id in self._id_modes[zone]:
                    self._id_modes[zone][ext_id] = SyncMode.FIFO
                    updated_ids.append(ext_id)

        if updated_ids:
            self.log_info(f"Updated IDs {updated_ids} to mode={mode} in zone='{zone}'")
        self.log_info(f"Ingest mode changed in '{zone}': {old} -> {mode}")