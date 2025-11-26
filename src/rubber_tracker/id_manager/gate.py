import os
import cv2
import yaml
import numpy as np
from rubber_tracker.utils import ModuleLogger

class Gate(ModuleLogger):
    def __init__(self, name1, name2,config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        self.mask_root = config["gates"]["mask_root"]
        self.masks = self._set_masks(name1, name2)

    def _set_masks(self, name1, name2):
        return {
            name1: self._load_mask(name1),
            name2: self._load_mask(name2),
        }

    def _load_mask(self, mask_name):
        if mask_name is None:
            return None
        
        mask_path = os.path.join(self.mask_root, mask_name+".png")
        if not os.path.exists(mask_path):
            raise FileNotFoundError(f"Mask not found: {mask_path}")

        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise FileNotFoundError(f"Mask not found: {mask_path}")

        self.log_info(f"Loaded mask: {mask_path}({mask.shape})")

        return (mask > 0)

    def bbox_hit_zone(self, bbox):
        for name, mask in self.masks.items():
            if self._check_collision(mask, bbox):
                return name
        return None

    def point_in_zone(self, center):
        for name, mask in self.masks.items():
            if self._check_fully_inside(mask, center):
                return name
        return None

    def _check_collision(self, mask, xyxy):
        """
        mask: boolean mask array (True where active)
        xyxy: (x1, y1, x2, y2), pixel coordinates
        """
        if mask is None:
            return False

        x1, y1, x2, y2 = map(int, xyxy)
        h, w = mask.shape

        # Clip
        x1 = max(0, min(x1, w - 1))
        x2 = max(0, min(x2, w))
        y1 = max(0, min(y1, h - 1))
        y2 = max(0, min(y2, h))

        if x2 <= x1 or y2 <= y1:
            return False

        roi = mask[y1:y2, x1:x2]
        return roi.any()

    def _check_fully_inside(self, mask, center):
        """
        center: (x, y)
        mask: boolean mask
        """
        if mask is None:
            return False

        x, y = map(int, center)
        h, w = mask.shape

        if not (0 <= x < w and 0 <= y < h):
            return False

        return mask[y, x]
