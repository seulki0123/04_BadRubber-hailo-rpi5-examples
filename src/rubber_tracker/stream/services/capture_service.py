# stream/services/capture_service.py
import os
import cv2
from datetime import datetime
from rubber_tracker.utils import ModuleLogger

class CaptureService(ModuleLogger):
    def __init__(self, output_dir, wr=2.0, hr=2.0):
        """
        wr: width ratio
        hr: height ratio
        """
        super().__init__(self.__class__.__name__)
        self.output_dir = output_dir
        self.wr = wr
        self.hr = hr

        os.makedirs(self.output_dir, exist_ok=True)

    def save_crop(self, track_id, speed, bbox, frame):
        """
        track_id: int
        speed: float
        bbox: [x1, y1, x2, y2]
        frame: numpy array (frame.im0)
        """

        h, w, _ = frame.shape

        x1, y1, x2, y2 = map(int, bbox)

        width = x2 - x1
        extra_w = int(width * (self.wr - 1) / 2)
        new_x1 = max(0, x1 - extra_w)
        new_x2 = min(w, x2 + extra_w)

        height = y2 - y1
        extra_h = int(height * (self.hr - 1) / 2)
        new_y1 = max(0, y1 - extra_h)
        new_y2 = min(h, y2 + extra_h)

        crop = frame[new_y1:new_y2, new_x1:new_x2]
        if crop is None or crop.size == 0:
            self.log_warning(f"Empty crop for track {track_id}")
            return None

        track_folder = os.path.join(self.output_dir, str(track_id))
        if not os.path.exists(track_folder):
            self.log_info(f"Creating track folder: {track_folder}")
            os.makedirs(track_folder)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        fname = f"{timestamp}_{speed:.4f}.jpg"
        path = os.path.join(track_folder, fname)

        cv2.imwrite(path, crop)
        # self.log_info(f"Saved crop: {path}")
        return crop
