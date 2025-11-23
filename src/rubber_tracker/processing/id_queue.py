from collections import deque

from rubber_tracker.utils import generate_color
from rubber_tracker.utils import ModuleLogger

class IDQueue(ModuleLogger):
    def __init__(self):
        super().__init__(self.__class__.__name__)
        self.available_ids = deque()
        self.used_ids = {}
        self.count = 0

    def assign(self, track_ids, bboxes):
        """
        track_ids: shape (N,) → [track_id1, track_id2, ...]
        bboxes: shape (N, 4) → [[xmin, ymin, xmax, ymax], [xmin, ymin, xmax, ymax], ...]
        N: number of bboxes
        """
        for track_id in track_ids:
            if track_id in self.used_ids:
                self.log_error(f"Track ID {track_id} is already used")
                continue
            self._assign_id(track_id)

    def release(self):
        pass

    def get_info(self, track_ids):
        return [
            self.used_ids.get(tid, {"id": None, "color": (0, 0, 0), "cnt": -1})
            for tid in track_ids
        ]
    
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

    def _release_id(self, track_id):
        # event when track is delted
        pass