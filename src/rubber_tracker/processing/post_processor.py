import yaml

from .tracker import Tracker
from .id_queue import IDQueue
from .gate_manager import GateManager
from .utils import EventMessage
from rubber_tracker.camera import Recorder
from rubber_tracker.utils import ModuleLogger
from rubber_tracker.detection.utils import Bboxes
from rubber_tracker.utils import CustomThread

class PostProcessor(ModuleLogger):
    def __init__(self, queue_getter, stream_status_getter, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.interval = config["post_processor"]["thread_interval"]
        self.score_threshold = config["detect"]["score_threshold"]
        self.scale_w = config["tracker"]["scale_w"]
        self.scale_h = config["tracker"]["scale_h"]
        self.draw_bboxes = config["post_processor"]["draw_bboxes"]
        self.draw_masks = config["post_processor"]["draw_masks"]
        self.draw_texts = config["post_processor"]["draw_texts"]
        
        self.gate_manager = GateManager()
        self.id_queue = IDQueue()
        self.tracker = Tracker()
        self.recorder = Recorder()
        self.event_messages = EventMessage()

        self.queue_getter = queue_getter
        self.stream_status_getter = stream_status_getter

    def _task(self):
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
        self.id_queue.assign(track_ids_new[in_spawn_zone])

        # remove old tracks
        removed_track_ids, removed_track_boxes = self.tracker.remove_old_tracks()
        
        # id queue finalize
        is_exit_zone = self.gate_manager.is_in_exit_zone(removed_track_boxes)
        self.id_queue.finalize_exit(removed_track_ids[is_exit_zone])
        self.id_queue.finalize_reject(removed_track_ids[~is_exit_zone])

        # draw bboxes
        if self.draw_bboxes:
            ext_info = self.id_queue.get_used_info(track_ids)
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

        # draw texts
        if self.draw_texts:
            # event message update
            finalized_info = self.id_queue.get_finalized_info()
            texts = [f"{tid}/{d['cnt']}/{d['id']}/{'exit' if d['exit'] else 'reject'}" for tid, d in finalized_info.items()]
            colors = [d['color'] for tid, d in finalized_info.items()]
            self.event_messages.add(texts, colors)
            # draw event messages
            texts, colors = self.event_messages.get()
            frame.draw_text(texts, colors)

        # record
        if self.recorder and self.stream_status_getter() is True:
            self.recorder.write_frame(frame.im, bboxes.xywhn)

    def start_thread(self):
        thread = CustomThread(name=self.__class__.__name__, task=self._task, interval=self.interval)
        thread.start()