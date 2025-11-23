import yaml

from .tracker import Tracker
from .id_queue import IDQueue
from .gate_manager import GateManager
from rubber_tracker.camera import Recorder
from rubber_tracker.utils import ModuleLogger
from rubber_tracker.detection.utils import Bboxes

class PostProcessor(ModuleLogger):
    def __init__(self, queue_getter, stream_status_getter, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.interval = config["post_processor"]["thread_interval"]
        self.score_threshold = config["detect"]["score_threshold"]
        self.scale_w = config["tracker"]["scale_w"]
        self.scale_h = config["tracker"]["scale_h"]
        self.draw_bboxes = config["post_processor_queue"]["draw_bboxes"]
        self.draw_masks = config["post_processor_queue"]["draw_masks"]
        
        self.gate_manager = GateManager()
        self.id_queue = IDQueue()
        self.tracker = Tracker()
        self.recorder = Recorder()

        self.queue_getter = queue_getter
        self.stream_status_getter = stream_status_getter

    def task(self):
        detection = self.queue_getter()
        if self.recorder and self.stream_status_getter() is False:
            self.recorder.stop()

        if detection is None:
            return

        frame, bboxes = detection
        bboxes_high, bboxes_low = bboxes.filter_by_score(self.score_threshold)

        # High-score boxes
        resized_bboxes = Bboxes.resize_xyxy(bboxes_high.xyxy, scale_w=self.scale_w, scale_h=self.scale_h)
        track_ids, is_new = self.tracker.update(resized_bboxes)

        # id queue assign
        track_ids_new = track_ids[is_new]
        bboxes_new = bboxes_high.xyxy[is_new]
        in_spawn_zone = self.gate_manager.is_in_spawn_zone(bboxes_new)
        self.id_queue.assign(track_ids_new[in_spawn_zone], bboxes_new[in_spawn_zone])

        # remove old tracks
        removed_track_ids = self.tracker.remove_old_tracks()
        if removed_track_ids:
            self.log_info(f"Removed {len(removed_track_ids)} old tracks: {removed_track_ids}")

        # draw bboxes
        if self.draw_bboxes:
            ext_info = self.id_queue.get_info(track_ids)
            draw_ids = [f"{tid}/{d['cnt']}/{d['id']}" for tid, d in zip(track_ids, ext_info)]
            draw_colors = [d['color'] for tid, d in zip(track_ids, ext_info)]
            frame.draw(bboxes_low.xyxy, bboxes_low.confs, bboxes_low.class_ids, None, None) # draw Low-score boxes
            frame.draw(bboxes_high.xyxy, bboxes_high.confs, bboxes_high.class_ids, draw_ids, draw_colors) # draw High-score boxes
            if self.scale_w != 1.0 or self.scale_h != 1.0:
                frame.draw(resized_bboxes, bboxes_high.confs, bboxes_high.class_ids, draw_ids, draw_colors) # draw resized track bboxes

        # draw masks
        if self.draw_masks:
            frame.draw_mask(self.gate_manager.input_mask1, color=(0, 0, 255))
            frame.draw_mask(self.gate_manager.input_mask2, color=(0, 0, 255))
            frame.draw_mask(self.gate_manager.output_mask1, color=(0, 255, 0))
            frame.draw_mask(self.gate_manager.output_mask2, color=(0, 255, 0))

        # record
        if self.recorder and self.stream_status_getter() is True:
            self.recorder.write_frame(frame.im, bboxes.xywhn)