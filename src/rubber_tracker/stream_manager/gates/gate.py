import os
import cv2

from rubber_tracker.utils import ModuleLogger, load_config

class Gate(ModuleLogger):
    """Represents a single zone (one mask)."""

    def __init__(self, name: str, mask_root: str = None):
        super().__init__(self.__class__.__name__)
        self.name = name
        config = load_config()

        # mask_root may be provided by GateManager
        self.mask_root = mask_root or config.get("gates", {}).get("mask_root")
        self.mask = None

        if self.name:
            self.mask = self._load_mask(self.name)

    def _load_mask(self, mask_name):
        if mask_name is None:
            return None
        if not self.mask_root:
            raise RuntimeError("mask_root not configured")

        mask_path = os.path.join(self.mask_root, mask_name + ".png")
        if not os.path.exists(mask_path):
            raise FileNotFoundError(f"Mask not found: {mask_path}")

        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise FileNotFoundError(f"Failed to read mask: {mask_path}")

        self.log_info(f"Loaded mask: {mask_path} ({mask.shape})")
        return (mask > 0)

    def bbox_hit_zone(self, bbox):
        """Return own name if bbox collides with mask, else None."""
        if self.mask is None:
            return None

        x1, y1, x2, y2 = map(int, bbox)
        h, w = self.mask.shape

        # Clip and validate
        x1 = max(0, min(x1, w - 1))
        x2 = max(0, min(x2, w))
        y1 = max(0, min(y1, h - 1))
        y2 = max(0, min(y2, h))

        if x2 <= x1 or y2 <= y1:
            return None

        roi = self.mask[y1:y2, x1:x2]
        if roi.any():
            return self.name
        return None

    def point_in_zone(self, center):
        if self.mask is None:
            return None

        x, y = map(int, center)
        h, w = self.mask.shape

        if not (0 <= x < w and 0 <= y < h):
            return None

        return self.name if self.mask[y, x] else None
