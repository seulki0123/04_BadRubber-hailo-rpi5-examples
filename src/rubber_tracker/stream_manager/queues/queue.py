from collections import deque

from rubber_tracker.utils import ModuleLogger

class Queue(ModuleLogger):
    def __init__(self, name):
        super().__init__(self.__class__.__name__ + "_" + (name or ""))
        self.name = name
        self._ext_ids = deque()        # 저장: (ext_id, baler)
        self._in_ext_ids = set()       # 저장: ext_id only

    def add(self, data):
        ext_id = data.get('id')
        if ext_id in self._in_ext_ids:
            self.log_warning(f"External ID '{ext_id}' already in queue {self.name}")
            return False

        self._ext_ids.append(data)
        self._in_ext_ids.add(ext_id)
        self.log_info(f"External ID {data} added to queue {self.name}")
        return True

    def get(self):
        if not self._ext_ids:
            self.log_warning(f"Queue {self.name} is empty")
            return None

        data = self._ext_ids.popleft()
        ext_id = data.get('id')
        self._in_ext_ids.discard(ext_id)
        return data