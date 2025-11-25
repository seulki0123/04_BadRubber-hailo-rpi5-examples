import time
import yaml

class Drawer():
    def __init__(self, stream_status_getter, tracks_info_getter, masks_getter, message_getter, config_path="config.yaml"):
        from rubber_tracker.camera import Recorder
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
        
        self.is_draw = config["drawer"]["draw"]
        self.record = config["drawer"]["record"]
        
        self.recorder = Recorder()
        self.stream_status_getter = stream_status_getter
        self.tracks_info_getter = tracks_info_getter
        self.masks_getter = masks_getter
        self.message_getter = message_getter


    def draw(self, frame, bboxes, confs, class_ids, track_ids):
        if self.is_draw:
            # bboxes
            ext_info = self.tracks_info_getter(track_ids)
            texts = []
            colors = []
            for track_id in track_ids:
                if track_id in ext_info:
                    ext_id = ext_info[track_id]['ext_id']
                    input_zone = ext_info[track_id]['input']
                    color = ext_info[track_id]['color']
                    texts.append(f"{track_id}/{ext_id}/{input_zone}")
                    colors.append(color)
                else:
                    texts.append(f"{track_id}")
                    colors.append((255, 255, 255))

            frame.draw(bboxes.xyxy, confs, class_ids, texts, colors)

            # masks
            for mask in self.masks_getter():
                frame.draw_mask(mask)

            # messages
            messages, colors = self.message_getter()
            frame.draw_text(messages, colors)
        
        if self.record:
            if self.recorder and self.stream_status_getter() is True:
                self.recorder.write_frame(frame.im, bboxes.xywhn)
            else:
                self.recorder.join()