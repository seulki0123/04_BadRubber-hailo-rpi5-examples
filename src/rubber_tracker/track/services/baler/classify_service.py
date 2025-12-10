import time

import numpy as np
from ultralytics import YOLO

from rubber_tracker.utils import ModuleLogger

class BalerClassifyService(ModuleLogger):
    """
    Handles the entire baler processing pipeline:
    - capture
    - crop
    - model inference
    - result update
    
    This is a domain-level service (not ML-centric).
    """

    def __init__(self, model_path, class_names, imgsz):
        super().__init__(self.__class__.__name__)
        self.model_path = model_path
        self.class_names = class_names
        self.imgsz = imgsz

        self.model = YOLO(self.model_path)
        self._warmup()

    def process(self, crop):
        if crop is None:
            return None
        return self._classify(crop)

    def _classify(self, crop_img):
        result = self.model(crop_img, imgsz=self.imgsz, verbose=False)
        result = result[0].probs.top1
        return result
        
    def _warmup(self):
        dummy_image = np.zeros((self.imgsz, self.imgsz, 3), dtype=np.uint8)
        self.model(dummy_image, imgsz=self.imgsz, verbose=False)