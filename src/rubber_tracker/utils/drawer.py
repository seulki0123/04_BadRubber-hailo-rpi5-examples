import time

from .utils import load_config

class Drawer():
    def __init__(self, stream_status_getter, tracks_info_getter, masks_getter, message_getter, recorder=None):
        # 멀티 프로파일에서 Drawer 는 프로파일마다 1개씩 생성되지만, 합성 프레임을
        # 기록하는 Recorder 는 1개로 충분하므로 외부에서 공용 Recorder 를 주입받는다.
        # 기존 단일 프로파일 호환을 위해, 주입이 없으면 내부에서 생성한다.
        if recorder is None:
            from rubber_tracker.camera import Recorder
            recorder = Recorder()
        self.recorder = recorder
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
                track = ext_info.get(track_id, None)
                if track is not None:
                    track = track.to_dict()
                    texts.append(track.get('info', f"{track_id}"))
                    colors.append(track.get('color', (128, 128, 128)))
                    text_colors.append(track.get('txt_color', (0, 255, 0)))
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