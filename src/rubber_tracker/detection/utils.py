import cv2
import hailo
import numpy as np

from hailo_apps_infra.hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
)

from rubber_tracker.utils import ModuleLogger

class Frame(ModuleLogger):
    def __init__(self, pad, buffer):
        super().__init__(__class__.__name__)
        
        caps = get_caps_from_pad(pad)
        self.format = caps[0]
        self.width = caps[1]
        self.height = caps[2]
        self.im0 = self.get_frame(buffer) # original image
        self.im = self.im0.copy()

    def get_frame(self, buffer):
        frame = get_numpy_from_buffer(buffer, self.format, self.width, self.height)
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def draw(self, bboxes, confs, labels, track_ids, colors):
        if track_ids is None:
            track_ids = [None] * len(bboxes)
        if colors is None:
            colors = [(128, 128, 128)] * len(bboxes)
        for bbox, conf, label, track_id, color in zip(bboxes, confs, labels, track_ids, colors):
            x1, y1, x2, y2 = map(int, bbox)
            # color = (0, 0, 255) if label == 1 else (0, 255, 0)
            cv2.rectangle(self.im, (x1, y1), (x2, y2), color, 2)
            cv2.putText(self.im, f"{track_id} {label} {conf:.2f}", (x1, y1+30), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)
    
    def draw_mask(self, mask, color=(0, 255, 0), alpha=0.4):
        if mask is None:
            return

        mask_bool = mask.astype(bool)

        mh, mw = mask_bool.shape
        fh, fw, _ = self.im.shape

        if (mh != fh) or (mw != fw):
            self.log_warning(f"Mask size {mw}x{mh} does not match frame size {fw}x{fh}. Using clipped region.")

        overlay = self.im.copy()

        h = min(mh, fh)
        w = min(mw, fw)

        overlay[0:h, 0:w][mask_bool[0:h, 0:w]] = color

        self.im = cv2.addWeighted(overlay, alpha, self.im, 1 - alpha, 0)

class Bboxes:
    def __init__(self, xywhn, confs, class_ids, width, height):
        self.width = width
        self.height = height
        self.xywhn = np.asarray(xywhn, dtype=np.float32)
        self.confs = np.asarray(confs, dtype=np.float32)
        self.class_ids = np.asarray(class_ids, dtype=np.int32)
        self.xyxy = self.xywhn2xyxy(xywhn, width, height) \
                     if xywhn.shape[0] > 0 \
                     else np.zeros((0, 4), dtype=np.float32)

    @staticmethod
    def xywhn2xyxy(xywhn, w, h):
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
    def xyxy2xywh(xyxy):
        x1, y1, x2, y2 = xyxy
        return (x1 + x2) / 2, (y1 + y2) / 2, x2 - x1, y2 - y1
    @staticmethod
    def xywh2xyxy(xywh):
        x, y, w, h = xywh
        return x - w / 2, y - h / 2, x + w / 2, y + h / 2
    @staticmethod
    def pixcel2norm(xyxy, width, height): # xyxy, xywh all ok
        x1, y1, x2, y2 = xyxy
        return x1 / width, y1 / height, x2 / width, y2 / height
    @staticmethod
    def norm2pixel(xyxy_norm, width, height): # xyxy, xywh all ok
        x1_norm, y1_norm, x2_norm, y2_norm = xyxy_norm
        return int(x1_norm * width), int(y1_norm * height), int(x2_norm * width), int(y2_norm * height)

    @staticmethod
    def resize_bboxes(bboxes: np.ndarray, scale_w: float, scale_h: float) -> np.ndarray:
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

    def filter_by_score(self, threshold: float):
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

def get_xwyh_and_conf_from_buffer(buffer):
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    xywh_norms = []
    confidences = []
    class_ids = []
    for detection in detections:
        # xywh_norms
        bbox = detection.get_bbox()
        xyxy = bbox.xmin(), bbox.ymin(), bbox.xmax(), bbox.ymax()
        xywh_norms.append(Bboxes.xyxy2xywh(xyxy))
        # confidences
        confidence = detection.get_confidence()
        confidences.append(round(confidence, 4))
        # class ids
        class_ids.append(detection.get_class_id())

    # 리스트 → NumPy 배열로 변환
    xywh_norms = np.array(xywh_norms, dtype=np.float32)
    confidences = np.array(confidences, dtype=np.float32)
    class_ids = np.array(class_ids, dtype=np.int32)

    return xywh_norms, confidences, class_ids


def parse_detection(pad, buffer):
    frame = Frame(pad, buffer)
    xywhn, confs, class_ids = get_xwyh_and_conf_from_buffer(buffer)
    bboxes = Bboxes(xywhn, confs, class_ids, frame.width, frame.height)
    return frame, bboxes