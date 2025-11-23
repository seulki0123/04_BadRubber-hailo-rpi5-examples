import cv2
import yaml
import numpy as np
from rubber_tracker.utils import ModuleLogger

class GateManager(ModuleLogger):
    def __init__(self, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        gate_cfg = config["gates"]

        # Load masks
        self.input_mask1 = self._load_mask(gate_cfg["masks"]["in1"])
        self.input_mask2 = self._load_mask(gate_cfg["masks"]["in2"])
        self.output_mask1 = self._load_mask(gate_cfg["masks"]["out1"])
        self.output_mask2 = self._load_mask(gate_cfg["masks"]["out2"])

        # Gate names
        self.input_name1 = gate_cfg["names"]["in1"]
        self.input_name2 = gate_cfg["names"]["in2"]
        self.output_name1 = gate_cfg["names"]["out1"]
        self.output_name2 = gate_cfg["names"]["out2"]

    def is_in_spawn_zone(self, xyxy):
        return (
            self._check_collision(self.input_mask1, xyxy) or
            self._check_collision(self.input_mask2, xyxy)
        )

    def _load_mask(self, mask_path):
        if mask_path is None:
            return None

        mask = cv2.imread(mask_path, cv2.IMREAD_GRAYSCALE)
        if mask is None:
            raise FileNotFoundError(f"Mask not found: {mask_path}")

        self.log_info(f"Loaded mask: {mask_path}({mask.shape})")

        return (mask > 0)

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