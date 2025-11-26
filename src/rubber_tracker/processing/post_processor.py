import yaml

from .tracker import Tracker
from .utils import EventMessage
from rubber_tracker.utils import ModuleLogger
from rubber_tracker.detection.utils import Bboxes
from rubber_tracker.utils import CustomThread

class PostProcessor(ModuleLogger):
    def __init__(self, 
        queue_getter,
        track_in_exit_zone_getter,
        track_created_callback,
        track_removed_callback,
        draw_callback,
        config_path="config.yaml",
    ):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.interval = config["post_processor"]["thread_interval"]
        self.score_threshold = config["detect"]["score_threshold"]
        self.scale_w = config["tracker"]["scale_w"]
        self.scale_h = config["tracker"]["scale_h"]
        self.exit_event_when_removed = config["post_processor"]["exit_event_when_removed"]
        
        self.tracker = Tracker()

        self.queue_getter = queue_getter
        self.track_in_exit_zone_getter = track_in_exit_zone_getter
        self.track_created_callback = track_created_callback
        self.track_removed_callback = track_removed_callback
        self.draw_callback = draw_callback

    def _task(self):
        detection = self.queue_getter()

        if detection is None:
            return

        frame, bboxes = detection
        bboxes_high, bboxes_low = bboxes.filter_by_score(self.score_threshold)

        # High-score boxes
        resized_bboxes = Bboxes.resize_xyxy(bboxes_high.xyxy, scale_w=self.scale_w, scale_h=self.scale_h)
        track_ids, is_new = self.tracker.update(resized_bboxes)

        # new track
        track_ids_new = track_ids[is_new]
        bboxes_new = bboxes_high.xyxy[is_new]
        if track_ids_new.size > 0:
            for track_id, bbox in zip(track_ids_new, bboxes_new):
                self.track_created_callback(track_id, bbox)

        # remove old tracks
        removed_track_ids, removed_track_boxes = self.tracker.remove_old_tracks()

        # exit event
        if self.exit_event_when_removed:
            if removed_track_ids.size > 0:
                for track_id, bbox in zip(removed_track_ids, removed_track_boxes):
                    self.track_removed_callback(track_id, bbox)

        else:
            # check if track is in exit zone
            for track_id, bbox in zip(track_ids, bboxes_high.xyxy):
                if self.track_in_exit_zone_getter(bbox) is not None:
                    self.track_removed_callback(track_id, bbox)

        # draw
        self.draw_callback(
            frame,
            bboxes_high,
            bboxes_high.confs,
            bboxes_high.class_ids,
            track_ids
        )
        
        # # draw texts
        # if self.draw_texts:
        #     # event message update
        #     finalized_info = self.id_queue.get_finalized_info()
        #     texts = [f"{tid}/{d['cnt']}/{d['id']}/{'exit' if d['exit'] else 'reject'}" for tid, d in finalized_info.items()]
        #     colors = [d['color'] for tid, d in finalized_info.items()]
        #     self.event_messages.add(texts, colors)
        #     # draw event messages
        #     texts, colors = self.event_messages.get()
        #     frame.draw_text(texts, colors)

    def start_thread(self):
        thread = CustomThread(name=self.__class__.__name__, task=self._task, interval=self.interval)
        thread.start()