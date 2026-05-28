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

        self._ingest_mode = initial_mode
        self._id_modes = {}

    # -------------------------
    # ID lifecycle operations
    # -------------------------
    def register(self, ext_id):
        with self._lock:
            self._id_modes[ext_id] = self._ingest_mode

        self.log_info(
            f"Registered ID '{ext_id}' "
            f"as mode={self._ingest_mode}"
        )

    def pop_id_mode(self, ext_id):
        with self._lock:
            return self._id_modes.pop(ext_id, None)

    def put_back(self, ext_id, mode):
        with self._lock:
            self._id_modes[ext_id] = mode

    # -------------------------
    # mode control
    # -------------------------
    def set_mode(self, mode):
        with self._lock:
            old = self._ingest_mode
            self._ingest_mode = mode

        self.log_info(
            f"Ingest mode changed: {old} -> {mode}"
        )

    def _mark_all_fifo(self, ids):
        with self._lock:
            for ext_id in ids:
                if ext_id in self._id_modes:
                    self._id_modes[ext_id] = SyncMode.FIFO

            self._ingest_mode = SyncMode.FIFO

        self.log_warning(
            f"Bulk FIFO transition applied "
            f"to {len(ids)} IDs"
        )

    def remove_ids(self, ids):
        with self._lock:
            for ext_id in ids:
                self._id_modes.pop(ext_id, None)