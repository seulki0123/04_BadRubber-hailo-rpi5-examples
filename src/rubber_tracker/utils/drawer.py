import time

from .utils import load_config

class Drawer():
    def __init__(self, stream_status_getter, tracks_info_getter, masks_getter, message_getter):
        config = load_config()
        from rubber_tracker.camera import Recorder
        
        self.recorder = Recorder()
        self.stream_status_getter = stream_status_getter
        self.tracks_info_getter = tracks_info_getter
        self.masks_getter = masks_getter
        self.message_getter = message_getter


    def draw(self, frame, bboxes, confs, class_ids, track_ids):
        if self.recorder and self.recorder._get_draw_state():
            # bboxes
            ext_info = self.tracks_info_getter(track_ids)
            texts = []
            colors = []
            text_colors = []
            for track_id in track_ids:
                if track_id in ext_info:
                    texts.append(ext_info[track_id].get('info', f"{track_id}"))
                    colors.append(ext_info[track_id].get('color', (128, 128, 128)))
                    text_colors.append(ext_info[track_id].get('txt_color', (0, 255, 0)))
                else:
                    texts.append(f"{track_id}")
                    colors.append((128, 128, 128))
                    text_colors.append((0, 0, 0))

            frame.draw(bboxes.xyxy, confs, class_ids, texts, colors, text_colors)

            # masks
            for mask in self.masks_getter():
                frame.draw_mask_outline(mask)

            # messages
            messages, colors = self.message_getter()
            frame.draw_text(messages, colors)
        
        if self.recorder and self.stream_status_getter() is True:
            self.recorder.write_frame(frame.im, bboxes.xywhn)
        else:
            self.recorder.join()