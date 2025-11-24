import copy
from collections import deque

from rubber_tracker.utils import generate_color
from rubber_tracker.utils import ModuleLogger

class Queue(ModuleLogger):
    def __init__(self, name):
        super().__init__(self.__class__.__name__ + "_" + name)
        self.name = name
        self.ext_ids = deque()
        self.in_ids = {}
        self.count = 0
    
    def add(self, ext_id):
        if ext_id in self.ext_ids:
            self.log_warning(f"External ID {ext_id} is already in the queue")
            return False

        if ext_id in self.in_ids:
            self.log_warning(f"External ID {ext_id} is already in the queue")
            return False

        self.ext_ids.append(ext_id)
        self.log_info(f"External ID {ext_id} added to the queue")

    def get(self):
        if not self.ext_ids:
            self.log_warning("Queue is empty")
            return None
        return self.ext_ids.popleft()