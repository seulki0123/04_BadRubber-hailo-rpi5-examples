import time
import queue

import yaml

from rubber_tracker.utils import ModuleLogger

class PostProcessorQueue(ModuleLogger):
    """Manages a queue of detection items"""
    def __init__(self, config_path="config.yaml"):
        super().__init__(self.__class__.__name__)
        
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        self.max_size = config["post_processor_queue"]["max_size"]
        self.logging_interval = config["post_processor_queue"]["logging_interval"]
        self.get_timeout = config["post_processor_queue"]["get_timeout"]
        
        self.queue = queue.Queue(maxsize=self.max_size)
        self.last_log_time = time.time()
    
    def add(self, frame, bboxes, class_ids):
        """Add a detection to the queue"""
        if not self.queue.full():
            self.queue.put((frame, bboxes, class_ids))
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