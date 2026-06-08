from collections import deque

from rubber_tracker.utils import ProcessLogger

class Queue(ProcessLogger):
    def __init__(self, name, max_size=None):
        super().__init__(self.__class__.__name__ + "_" + (name or ""))
        self.name = name
        self.max_size = max_size

        self._ext_ids = deque()
        self._in_ext_ids = set()

    def add(self, data):
        ext_id = data.get('id')
        if ext_id is None:
            self.log_warning(f"[add] Data without 'id' cannot be added to queue {self.name}")
            return False, None
            
        if ext_id in self._in_ext_ids:
            self.log_warning(f"[add] External ID '{ext_id}' already in queue {self.name}")
            return False, None

        if self.max_size is not None and len(self._ext_ids) >= self.max_size:
            removed = self._remove_oldest()
            self.log_warning(
                f"Queue {self.name} max_size={self.max_size}, "
                f"removed oldest: {removed}"
            )
        else:
            removed = None

        self._ext_ids.append(data)
        self._in_ext_ids.add(ext_id)
        self.log_info(f"External ID {data} added to queue {self.name}")
        return True, removed

    def get(self):
        if not self._ext_ids:
            self.log_warning(f"Queue {self.name} is empty")
            return None

        data = self._ext_ids.popleft()
        ext_id = data.get('id')
        self._in_ext_ids.discard(ext_id)
        return data

    def add_left(self, data):
        ext_id = data.get('id')

        if ext_id is None:
            self.log_warning(
                f"[add_left] Data without 'id' cannot be added to queue {self.name}"
            )
            return False, None

        if ext_id in self._in_ext_ids:
            self.log_warning(
                f"[add_left] External ID '{ext_id}' already in queue {self.name}"
            )
            return False, None

        removed = None

        if self.max_size is not None and len(self._ext_ids) >= self.max_size:
            removed = self._ext_ids.pop()
            self._in_ext_ids.discard(removed["id"])

            self.log_warning(
                f"Queue {self.name} max_size={self.max_size}, "
                f"removed newest: {removed}"
            )

        self._ext_ids.appendleft(data)
        self._in_ext_ids.add(ext_id)

        return True, removed

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