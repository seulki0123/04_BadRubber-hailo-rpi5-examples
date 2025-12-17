import os
import time
from datetime import datetime

import cv2

from rubber_tracker.utils import ProcessLogger, load_config

class Recorder(ProcessLogger):
    def __init__(self):
        super().__init__(__class__.__name__)
        config = load_config()
        save_root, record, save_frames, draw = self._get_save_config()
        self.draw = draw
        self.record = record
        self.save_root = save_root
        self.save_frames = save_frames
        self.vid_path, self.frame_dir = self._save_dir()

        self.fps = config["ipcamera"]["fps"]

        self.writer = None
        self.is_recording = True

        self.frame_count = 0

        self.update_interval = config["recorder"]["update_interval"]
        self.last_update_time = time.time()

    def _start(self, w, h):
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.writer = cv2.VideoWriter(self.vid_path, fourcc, self.fps, (w, h))
        self.log_info(f"Started recording to {self.vid_path}")

    def write_frame(self, frame, bboxes):
        self.frame_count += 1

        if time.time() - self.last_update_time > self.update_interval:
            self.last_update_time = time.time()
            if self._update_state():
                return

        if not self.record:
            return

        if not self.is_recording:
            return

        if self.writer is None:
            h, w = frame.shape[:2]
            self._start(w, h)

        if self.writer is not None:
            self.writer.write(frame)
        
        if self.save_frames:
            self._save_frame(frame, bboxes)

    def join(self):
        if self.writer is not None:
            self.writer.release()
            self.writer = None
            self.log_info("Stopped recording.")
        self.is_recording = False

    def _save_dir(self):
        config = load_config()

        filename1 = os.path.basename(config["ipcamera"]["url1"])
        filename2 = os.path.basename(config["ipcamera"]["url2"]) if config["ipcamera"]["url2"] else "null"
        video_name = f"{filename1}_{filename2}.mp4"

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        save_dir = os.path.join(self.save_root, f"{timestamp}_{video_name}")

        vid_path = os.path.join(save_dir, video_name)
        frame_dir = os.path.join(save_dir, "frames")

        os.makedirs(frame_dir, exist_ok=True)

        self.log_info(f"Save directory created: {save_dir}")

        return vid_path, frame_dir

    def _save_frame(self, frame, bboxes):
        filename = f"frame_{self.frame_count:06d}.jpg"
        filepath = os.path.join(self.frame_dir, filename)
        cv2.imwrite(filepath, frame)
        with open(filepath.replace(".jpg", ".txt"), "w") as f:
            for bbox in bboxes:
                f.write(f"{' '.join(map(str, bbox))}\n") # xywhn

    def _get_save_config(self):
        config = load_config()
        save_root = config["recorder"]["save_root"]
        record = config["recorder"]["record"]
        save_frames = config["recorder"]["save_frames"]
        draw = config["recorder"]["draw"]
        return save_root, record, save_frames, draw

    def _get_draw_state(self):
        return self.draw
        
    def _update_state(self):
        save_root, record, save_frames, draw = self._get_save_config()

        if save_root != self.save_root \
            or record != self.record \
            or save_frames != self.save_frames \
            or draw != self.draw:

            # init
            self.join()
            self.is_recording = True

            # update
            self.draw = draw
            self.record = record
            self.save_root = save_root
            self.save_frames = save_frames
            self.vid_path, self.frame_dir = self._save_dir()

            self.log_info(f"Recorder state updated")

            return True
        
        return False