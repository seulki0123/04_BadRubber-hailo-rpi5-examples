from rubber_tracker.utils import ModuleLogger

class SpeedService(ModuleLogger):
    def __init__(self, min_threshold):
        super().__init__(self.__class__.__name__)
        self.min_threshold = min_threshold

    def is_slow(self, speed) -> bool:
        return speed <= self.min_threshold