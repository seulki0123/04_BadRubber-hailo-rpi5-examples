import yaml

from rubber_tracker.utils import ModuleLogger

class PostProcessor(ModuleLogger):
    def __init__(self, queue_getter, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)["post_processor"]

        self.interval = config["thread_interval"]

        self.queue_getter = queue_getter

    def task(self):
        detection = self.queue_getter()
        if detection is None:
            return

        frame, bboxes, class_ids = detection