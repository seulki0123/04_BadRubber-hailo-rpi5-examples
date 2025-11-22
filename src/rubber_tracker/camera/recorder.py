import os

import cv2
import yaml

from rubber_tracker.utils import ModuleLogger

class Recorder(ModuleLogger):
    def __init__(self, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.save_frames = config["recorder"]["save_frames"]

        save_root = config["recorder"]["save_root"]
        filename1 = os.path.basename(config["ipcamera"]["url1"])
        filename2 = os.path.basename(config["ipcamera"]["url2"])
        filename = f"{filename1}_{filename2}.mp4"
        save_dir = os.path.join(save_root, filename)
        self.save_video_path = os.path.join(save_dir, filename)
        self.save_frames_dir = os.path.join(save_dir, "frames")
        os.makedirs(self.save_frames_dir, exist_ok=True)

        self.fps = config["ipcamera"]["fps"]

        self.writer = None
        self.is_recording = True

        self.frame_count = 0

    def _start(self, w, h):
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.writer = cv2.VideoWriter(self.save_video_path, fourcc, self.fps, (w, h))
        self.log_info(f"Started recording to {self.save_video_path}")

    def write_frame(self, frame, bboxes):
        if not self.is_recording:
            return

        if self.writer is None:
            h, w = frame.shape[:2]
            self._start(w, h)

        if self.is_recording and self.writer is not None:
            self.writer.write(frame)
        
        if self.save_frames:
            self._save_frame(frame, bboxes)

        self.frame_count += 1

    def stop(self):
        if self.writer is not None:
            self.writer.release()
            self.writer = None
            self.log_info("Stopped recording.")
        self.is_recording = False

    def is_active(self):
        return self.is_recording

    def _save_frame(self, frame, bboxes):
        filename = f"frame_{self.frame_count:06d}.jpg"
        filepath = os.path.join(self.save_frames_dir, filename)
        cv2.imwrite(filepath, frame)
        with open(filepath.replace(".jpg", ".txt"), "w") as f:
            for bbox in bboxes:
                f.write(f"{' '.join(map(str, bbox))}\n") # xywhn