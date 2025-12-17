import os
import cv2

from rubber_tracker.utils import ProcessLogger

class MaskLoader(ProcessLogger):
    """Loads masks from disk and resizes them for a target image shape."""

    def __init__(self, mask_root):
        super().__init__(self.__class__.__name__)
        self.mask_root = mask_root

    def load_mask(self, name):
        path = os.path.join(self.mask_root, name + ".png")
        mask = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise FileNotFoundError(f"Mask not found or invalid: {path}")
        return (mask > 0).astype("uint8")

    def load_and_resize(self, name, target_w, target_h):
        mask = self.load_mask(name)
        mask_h, mask_w = mask.shape
        if not (mask_w == target_w and mask_h == target_h):
            self.log_warning(f"Mask {name} size mismatch: {mask_w}x{mask_h} != {target_w}x{target_h} (resize will be applied)")
            resized = cv2.resize(mask, (target_w, target_h), interpolation=cv2.INTER_NEAREST)
            return resized
        return mask

    def load_multi(self, names, target_w, target_h):
        result = {}
        for n in names:
            result[n] = self.load_and_resize(n, target_w, target_h)
        return result