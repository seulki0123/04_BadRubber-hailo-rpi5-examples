import queue
from typing import Optional, Callable, Any, List
from rubber_tracker.utils import ModuleLogger

class ClassificationBuffer(ModuleLogger):
    """
    Simple queue buffer storing batch items: (track_id:int, crops:list, callback)
    """
    def __init__(self, max_size: int = 300):
        super().__init__(self.__class__.__name__)
        self.queue = queue.Queue(maxsize=max_size)

    def put(self, track_id: int, crops: List[Any], callback: Optional[Callable]) -> bool:
        try:
            self.queue.put_nowait((track_id, crops, callback))
            return True
        except queue.Full:
            self.log_warning(f"Classification buffer full, dropping batch (dropped size={len(crops)})")
            return False

    def get(self, timeout: float = 0.02):
        try:
            return self.queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def qsize(self) -> int:
        return self.queue.qsize()