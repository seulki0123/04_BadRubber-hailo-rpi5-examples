import yaml

from rubber_tracker.camera import Recorder
from rubber_tracker.utils import ModuleLogger

class PostProcessor(ModuleLogger):
    def __init__(self, queue_getter, stream_status_getter, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)["post_processor"]

        self.interval = config["thread_interval"]

        self.recorder = Recorder()

        self.queue_getter = queue_getter
        self.stream_status_getter = stream_status_getter

    def task(self):
        detection = self.queue_getter()
        if detection is None:
            return

        frame, bboxes, class_ids = detection
        if bboxes.xyxy is not None:
            track_ids = [None] * len(bboxes.xyxy)
            frame.draw(bboxes.xyxy, bboxes.confs, class_ids, track_ids)

        if self.recorder:
            if self.stream_status_getter() is True:
                self.recorder.write_frame(frame.im, bboxes.xywhn)
            else:
                self.recorder.stop()