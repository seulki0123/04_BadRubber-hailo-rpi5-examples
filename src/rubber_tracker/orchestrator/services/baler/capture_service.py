import os
import cv2

from rubber_tracker.utils import ModuleLogger

class CaptureService(ModuleLogger):
    def __init__(self, save_root, wr=2.0, hr=2.0):
        """
        wr: width ratio
        hr: height ratio
        """
        super().__init__(self.__class__.__name__)
        self.save_root = save_root
        self.wr = wr
        self.hr = hr

    def crop(self, bbox, frame, save_path=None):
        """
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
            self.log_warning(f"Empty crop")
            return None
        
        if save_path is not None:
            save_path = os.path.join(self.save_root, save_path)
            save_dir = os.path.dirname(save_path)
            if not os.path.exists(save_dir):
                self.log_info(f"Creating save directory: {save_dir}")
                os.makedirs(save_dir)

            cv2.imwrite(save_path, crop)

        return crop
