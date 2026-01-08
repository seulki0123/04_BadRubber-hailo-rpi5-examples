import time
import queue

from utils import ProcessLogger

class Queue(ProcessLogger):
    def __init__(
        self,
        name: str,
        max_size: int,
        get_timeout=0.0,
        logging_interval=0.0,
    ):
        super().__init__(f"{name}_{self.__class__.__name__}")
        self.max_size = max_size
        self.get_timeout = get_timeout
        self.logging_interval = logging_interval
        
        self.queue = queue.Queue(maxsize=self.max_size)
        self.last_log_time = time.time()
    
    def add(self, data):
        try:
            self.queue.put_nowait(data)
        except queue.Full:
            try:
                _ = self.queue.get_nowait()  # drop old
                self.log_warning(f"Queue is full, dropping old item")
            except queue.Empty:
                pass
            self.queue.put_nowait(data)      # put new

        if self.logging_interval != 0.0:
            now = time.time()
            if now - self.last_log_time >= self.logging_interval:
                self.log_info(f"Queue size: {self.queue.qsize()}")
                self.last_log_time = now

    def get(self):
        try:
            item = self.queue.get(timeout=self.get_timeout)
            return item
        except queue.Empty:
            return None
            
    def is_empty(self):
        return self.queue.empty()
        
    def size(self):
        return self.queue.qsize()