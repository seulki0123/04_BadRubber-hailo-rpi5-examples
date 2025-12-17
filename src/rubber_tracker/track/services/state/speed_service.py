from rubber_tracker.utils import ProcessLogger

class SpeedService(ProcessLogger):
    def __init__(self, min_threshold, max_threshold):
        super().__init__(self.__class__.__name__)
        self.min_threshold = min_threshold
        self.max_threshold = max_threshold

    def is_slow(self, speed) -> bool:
        return self.min_threshold < speed <= self.max_threshold
    
    def is_stop(self, speed) -> bool:
        return speed <= self.min_threshold