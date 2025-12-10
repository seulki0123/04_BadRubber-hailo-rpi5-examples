import os
from datetime import datetime

import cv2

from rubber_tracker.utils import ModuleLogger

class CaptureService(ModuleLogger):
    def __init__(self, wr=2.0, hr=2.0, save=False, save_dir="results/captures"):
        """
        wr: width ratio
        hr: height ratio
        """
        super().__init__(self.__class__.__name__)
        self.wr = wr
        self.hr = hr
        self.save = save
        self.save_dir = self._get_save_dir(save_dir)

    def crop(self, bbox, frame, save_folder=None, save_infos=[]):
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
        
        if self.save and save_folder is not None:
            save_path = self.set_save_path(save_folder, save_infos)
            cv2.imwrite(save_path, crop)

        return crop

    def set_save_path(self, save_folder, save_infos):
        now = datetime.now()
        timestamp = now.strftime("%Y%m%d-%H%M%S") + f"-{now.microsecond // 1000:03d}"
        save_name = f"{save_folder}_{timestamp}.jpg" + "_" + "_".join(map(str, save_infos)) + ".jpg"
        save_path = os.path.join(self.save_dir, str(save_folder), save_name)
        save_dir = os.path.dirname(save_path)
        os.makedirs(save_dir, exist_ok=True)
        return save_path

    def _get_save_dir(self, base_dir):
        if not self.save:
            return None

        if not os.path.exists(base_dir):
            os.makedirs(base_dir, exist_ok=False)
            return base_dir

        self.log_warning(f"Save directory '{base_dir}' already exists. Creating a new numbered directory.")

        counter = 1
        new_dir = f"{base_dir}_{counter}"
        while os.path.exists(new_dir):
            counter += 1
            new_dir = f"{base_dir}_{counter}"

        os.makedirs(new_dir, exist_ok=False)
        return new_dir