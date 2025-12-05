
from .tracker import Tracker
from rubber_tracker.detection.utils import Bboxes
from rubber_tracker.utils import ModuleLogger, CustomThread, load_config

class PostProcessor(ModuleLogger):
    def __init__(self, queue_getter, event_handler, draw_callback=None):
        super().__init__(__class__.__name__)
        config = load_config()

        self.interval = config["post_processor"]["thread_interval"]
        self.score_threshold = config["detect"]["score_threshold"]
        self.scale_w = config["tracker"]["scale_w"]
        self.scale_h = config["tracker"]["scale_h"]
        self.containment_threshold = config["post_processor"]["containment_threshold"]

        self.queue_getter = queue_getter
        self.tracker = Tracker()

        # event callbacks (provided by PipelineManager)
        self.event_handler = event_handler
        self.draw_callback = draw_callback


    def _task(self):
        detection = self.queue_getter()
        if detection is None:
            return

        frame, bboxes = detection
        
        # filtering
        bboxes_high, bboxes_low = bboxes.filter_by_score(self.score_threshold)
        bboxes_high = bboxes_high.remove_contained(self.containment_threshold)

        # tracking
        resized_bboxes = Bboxes.resize_xyxy(bboxes_high.xyxy, scale_w=self.scale_w, scale_h=self.scale_h)
        track_ids, is_new = self.tracker.update(resized_bboxes)

        # new track events
        track_ids_new = track_ids[is_new]
        bboxes_new = bboxes_high.xyxy[is_new]
        for track_id, bbox in zip(track_ids_new, bboxes_new):
            self.event_handler.on_created(track_id, bbox)

        # update events (for all active tracks)
        for track_id, bbox in zip(track_ids, bboxes_high.xyxy):
            self.event_handler.on_updated(track_id, bbox, frame.im0)
            
        # removed tracks
        removed_track_ids, removed_track_boxes = self.tracker.remove_old_tracks()
        for track_id, bbox in zip(removed_track_ids, removed_track_boxes):
            self.event_handler.on_removed(track_id, bbox)

        # draw
        if self.draw_callback:
            frame.draw(bboxes.xyxy, bboxes.confs, bboxes.class_ids, None, None)
            self.draw_callback(frame, bboxes_high, bboxes_high.confs, bboxes_high.class_ids, track_ids)

    def start_thread(self):
        thread = CustomThread(name=self.__class__.__name__, task=self._task, interval=self.interval)
        thread.start()