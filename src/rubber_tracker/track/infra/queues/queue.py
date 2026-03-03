from collections import deque

from rubber_tracker.utils import ProcessLogger

class Queue(ProcessLogger):
    def __init__(self, name, just_one_id: bool = False):
        super().__init__(self.__class__.__name__ + "_" + (name or ""))
        self.name = name
        self._ext_ids = deque(maxlen=1 if just_one_id else None)        # 저장: (ext_id, baler)
        self._in_ext_ids = set()                                        # 저장: ext_id only
        self.just_one_id = just_one_id

    def add(self, data):
        ext_id = data.get('id')
        if ext_id is None:
            self.log_warning(f"Data without 'id' cannot be added to queue {self.name}")
            return False
            
        if ext_id in self._in_ext_ids:
            self.log_warning(f"External ID '{ext_id}' already in queue {self.name}")
            return False

        if self.just_one_id:
            self._remove_oldest()

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

    def add_left(self, data):
        if self.just_one_id:
            return self.add(data)
        self._ext_ids.appendleft(data)
        return True

    def clear(self):
        removed_ids = [item['id'] for item in self._ext_ids]
        self._ext_ids.clear()
        self._in_ext_ids.clear()
        self.log_info(f"Queue {self.name} cleared ({len(removed_ids)} items removed)")
        return removed_ids

    def __len__(self):
        return len(self._ext_ids)

    def _remove_oldest(self):
        if not self._ext_ids:
            return None

        old = self._ext_ids.popleft()
        old_id = old.get('id')
        self._in_ext_ids.discard(old_id)
        self.log_info(f"Queue {self.name}: replaced old ID {old_id}")
        return old