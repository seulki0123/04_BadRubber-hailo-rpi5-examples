import time
import queue

from rubber_tracker.utils import ProcessLogger, load_config

class DetectionBuffer(ProcessLogger):
    """Manages a queue of detection items"""
    def __init__(self):
        super().__init__(self.__class__.__name__)
        config = load_config()
        self.max_size = config["detection_queue"]["max_size"]
        self.logging_interval = config["detection_queue"]["logging_interval"]
        self.get_timeout = config["detection_queue"]["get_timeout"]
        
        self.queue = queue.Queue(maxsize=self.max_size)
        self.last_log_time = time.time()
    
    def add(self, frame, bboxes):
        """Add a detection to the queue"""
        if not self.queue.full():
            self.queue.put((frame, bboxes))
            if time.time() - self.last_log_time >= self.logging_interval:
                self.log_info(f"Queue size: {self.queue.qsize()}")
                self.last_log_time = time.time()
        else:
            self.log_warning(f"Detection queue is full. Queue size: {self.queue.qsize()}")
    
    def get(self):
        """Get a detection from the queue with a timeout to prevent busy-waiting"""
        try:
            item = self.queue.get(timeout=self.get_timeout)
            self.log_debug(f"Getting detection from queue. Queue size after get: {self.queue.qsize()}")
            return item
        except queue.Empty:
            return None
            
    def is_empty(self):
        """Check if the queue is empty"""
        return self.queue.empty()
        
    def size(self):
        """Get the current size of the queue"""
        return self.queue.qsize()