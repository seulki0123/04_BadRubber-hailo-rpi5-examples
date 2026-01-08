from __future__ import annotations

import numpy as np
from numpy.typing import ArrayLike

class Bboxes:
    def __init__(self, xywhn: ArrayLike, confs: ArrayLike, class_ids: ArrayLike, width: int, height: int):
        self.width: int = width
        self.height: int = height
        self.xywhn: np.ndarray = np.asarray(xywhn, dtype=np.float32)
        self.confs: np.ndarray = np.asarray(confs, dtype=np.float32)
        self.class_ids: np.ndarray = np.asarray(class_ids, dtype=np.int32)
        self.xyxy: np.ndarray = self.xywhn2xyxy(self.xywhn, width, height) \
                                if self.xywhn.shape[0] > 0 \
                                else np.zeros((0, 4), dtype=np.float32)
        
    @staticmethod
    def xywhn2xyxy(xywhn: np.ndarray, w: int, h: int) -> np.ndarray:
        """
        xywhn: shape (N,4) → [x_center_norm, y_center_norm, w_norm, h_norm]
        return: shape (N,4) → [xmin, ymin, xmax, ymax]
        """
        xyxy = np.zeros_like(xywhn)
        xyxy[:, 0] = (xywhn[:, 0] - xywhn[:, 2] / 2) * w  # xmin
        xyxy[:, 1] = (xywhn[:, 1] - xywhn[:, 3] / 2) * h  # ymin
        xyxy[:, 2] = (xywhn[:, 0] + xywhn[:, 2] / 2) * w  # xmax
        xyxy[:, 3] = (xywhn[:, 1] + xywhn[:, 3] / 2) * h  # ymax
        return xyxy
        
    @staticmethod
    def xyxy2xywh(xyxy: np.ndarray) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = xyxy
        return (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
    @staticmethod
    def xywh2xyxy(xywh: np.ndarray) -> tuple[float, float, float, float]:
        x, y, w, h = xywh
        return x - w / 2, y - h / 2, x + w / 2, y + h / 2
    @staticmethod
    def pixel2norm(xyxy: np.ndarray, width: int, height: int) -> tuple[float, float, float, float]:
        x1, y1, x2, y2 = xyxy
        return x1 / width, y1 / height, x2 / width, y2 / height
    @staticmethod
    def norm2pixel(xyxy_norm: np.ndarray, width: int, height: int) -> tuple[int, int, int, int]:
        x1_norm, y1_norm, x2_norm, y2_norm = xyxy_norm
        return int(x1_norm * width), int(y1_norm * height), int(x2_norm * width), int(y2_norm * height)

    @staticmethod
    def resize_xyxy(bboxes: np.ndarray, scale_w: float, scale_h: float) -> np.ndarray:
        if scale_w == 1.0 and scale_h == 1.0:
            return bboxes
            
        bboxes = bboxes.astype(np.float32, copy=False)
        
        cx = (bboxes[:, 0] + bboxes[:, 2]) / 2
        cy = (bboxes[:, 1] + bboxes[:, 3]) / 2

        w = (bboxes[:, 2] - bboxes[:, 0]) * scale_w
        h = (bboxes[:, 3] - bboxes[:, 1]) * scale_h

        new_bboxes = np.stack([
            cx - w / 2,
            cy - h / 2,
            cx + w / 2,
            cy + h / 2
        ], axis=1)

        return new_bboxes
    
    @staticmethod
    def get_centers(xyxy: np.ndarray) -> np.ndarray:
        xc = (xyxy[:, 0] + xyxy[:, 2]) / 2
        yc = (xyxy[:, 1] + xyxy[:, 3]) / 2
        return np.stack([xc, yc], axis=1).astype(np.float16)

    @staticmethod
    def get_center(xyxy: np.ndarray) -> tuple[float, float]:
        x1, y1, x2, y2 = xyxy
        cx = (x1 + x2) / 2
        cy = (y1 + y2) / 2
        return cx, cy

    @staticmethod
    def get_containment_mask(xyxy: np.ndarray, threshold: float = 0.8) -> np.ndarray:
        if len(xyxy) == 0:
            return np.ones(0, dtype=bool)

        xyxy = xyxy.astype(np.float32)

        A = xyxy[:, None, :]
        B = xyxy[None, :, :]

        # intersection
        inter_x1 = np.maximum(A[..., 0], B[..., 0])
        inter_y1 = np.maximum(A[..., 1], B[..., 1])
        inter_x2 = np.minimum(A[..., 2], B[..., 2])
        inter_y2 = np.minimum(A[..., 3], B[..., 3])

        inter_w = np.clip(inter_x2 - inter_x1, 0, None)
        inter_h = np.clip(inter_y2 - inter_y1, 0, None)
        inter_area = inter_w * inter_h

        area_A = (A[..., 2] - A[..., 0]) * (A[..., 3] - A[..., 1])
        area_B = (B[..., 2] - B[..., 0]) * (B[..., 3] - B[..., 1])

        # A must be smaller than B
        smaller = area_A < area_B

        # fraction of A inside B
        containment = inter_area / (area_A + 1e-6)

        # "A is mostly inside B" AND "A is smaller than B"
        remove_mask = (containment >= threshold) & smaller
        remove_mask = remove_mask.any(axis=1)

        return ~remove_mask

    def filter_by_score(self, threshold: float) -> tuple[Bboxes, Bboxes]:
        """
        Return:
            high_scores: Bboxes  (score >= threshold)
            low_scores:  Bboxes  (score <  threshold)
        """
        mask_high = self.confs >= threshold
        mask_low = ~mask_high

        high_boxes = Bboxes(
            self.xywhn[mask_high],
            self.confs[mask_high],
            self.class_ids[mask_high],
            self.width,
            self.height
        )

        low_boxes = Bboxes(
            self.xywhn[mask_low],
            self.confs[mask_low],
            self.class_ids[mask_low],
            self.width,
            self.height
        )

        return high_boxes, low_boxes

    def remove_contained(self, threshold: float = 0.8) -> Bboxes:
        keep_mask = self.get_containment_mask(self.xyxy, threshold)

        return Bboxes(
            self.xywhn[keep_mask],
            self.confs[keep_mask],
            self.class_ids[keep_mask],
            self.width,
            self.height
        )