import copy
from collections import deque

from rubber_tracker.utils import generate_color
from rubber_tracker.utils import ModuleLogger

class IDQueue(ModuleLogger):
    def __init__(self):
        super().__init__(self.__class__.__name__)
        self.available_ids = deque()
        self.used_ids = {} # track_id: {'id': ext_id, 'color': color, 'cnt': cnt}
        self.finalized_ids = {} # track_id: {'id': ext_id, 'color': color, 'cnt': cnt, 'exit': bool}
        self.count = 0

    def assign(self, track_ids):
        """
        track_ids: shape (N,) → [track_id1, track_id2, ...]
        """
        for track_id in track_ids:
            if track_id in self.used_ids:
                self.log_error(f"Track ID {track_id} is already used")
                continue
            self._assign_id(track_id)

    def get_used_info(self, track_ids):
        return [
            self.used_ids.get(tid, {"id": None, "color": (0, 0, 0), "cnt": -1})
            for tid in track_ids
        ]


    def finalize_exit(self, track_ids):
        for track_id in track_ids:
            if track_id not in self.used_ids:
                self.log_error(f"Track ID {track_id} is not used")
                continue
            self._finalize_id(track_id, True)

    def finalize_reject(self, track_ids):
        for track_id in track_ids:
            if track_id not in self.used_ids:
                self.log_error(f"Track ID {track_id} is not used")
                continue
            self._finalize_id(track_id, False)

    def get_finalized_info(self):
        info = copy.deepcopy(self.finalized_ids)
        self.finalized_ids.clear()
        return info
    

    def add_external_id(self, ext_id):
        if ext_id in self.used_ids:
            self.log_error(f"External ID {ext_id} is already used")
            return False
        
        if ext_id in self.available_ids:
            self.log_error(f"External ID {ext_id} is already available")
            return False
        
        self.available_ids.append(ext_id)
        self.log_info(f"External ID added: {ext_id}")


    def _assign_id(self, track_id):
        if not self.available_ids:
            ext_id = "X"
            color = (255, 255, 255)
            self.log_error("No available IDs")
        else:
            ext_id = self.available_ids.popleft()
            color = generate_color()
            self.log_info(f"Assigned ID {ext_id} to track {track_id}")        
        
        self.used_ids[track_id] = {'id': ext_id, 'color': color, 'cnt': self.count}
        self.count += 1

    def _finalize_id(self, track_id, is_exit):
        if not track_id in self.used_ids:
            self.log_info(f"Track ID {track_id} is not used")
            return None

        self.finalized_ids[track_id] = copy.deepcopy(self.used_ids[track_id])
        self.finalized_ids[track_id]['exit'] = is_exit
        del self.used_ids[track_id]

        self.log_info(f"Finalized ID {self.finalized_ids[track_id]['id']} for track {track_id}, {'exit' if is_exit else 'reject'}")