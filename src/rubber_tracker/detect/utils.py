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

    def draw(self, bboxes, confs, labels, track_ids, colors=None, text_colors=None):
        default_color = (222, 222, 222)
        default_text_color = (255, 255, 255)
        if track_ids is None:
            track_ids = [None] * len(bboxes)
        if colors is None:
            colors = [default_color] * len(bboxes)
        if text_colors is None:
            text_colors = [default_text_color] * len(bboxes)

        for bbox, conf, label, track_id, color, text_color in zip(bboxes, confs, labels, track_ids, colors, text_colors):
            text_color = text_color if text_color is not None else default_text_color
            color = color if color is not None else default_color

            x1, y1, x2, y2 = map(int, bbox)

            # Draw main bounding box
            cv2.rectangle(self.im, (x1, y1), (x2, y2), color, 2)

            # Cetner
            center = (x1 + x2) / 2, (y1 + y2) / 2
            cv2.circle(self.im, tuple(map(int, center)), 5, color, -1)

            # Label Box
            text = f"{track_id} {label} {conf:.2f}"
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.6
            thickness = 2

            # Text Size
            (tw, th), _ = cv2.getTextSize(text, font, font_scale, thickness)

            # Label Box Coordinates
            label_x1 = x1
            label_y1 = y1 - th - 8
            label_x2 = x1 + tw + 6
            label_y2 = y1

            # If label box goes above the image, push it down
            if label_y1 < 0:
                label_y1 = y1
                label_y2 = y1 + th + 8

            # Filled rectangle (label background)
            cv2.rectangle(self.im, (label_x1, label_y1), (label_x2, label_y2), color, -1)

            # Put text on label box
            cv2.putText(
                self.im, text,
                (label_x1 + 3, label_y2 - 5),
                font, font_scale,
                text_color, 1
            )
    
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

    def draw_mask_outline(self, mask, color=(0, 255, 0), thickness=1):
        """
        Draw only the outline (contour) of a binary mask on the frame.
        """
        if mask is None:
            return

        # mask → uint8 변환
        mask_uint8 = (mask.astype(np.uint8) * 255)

        # 윤곽선 추출 (opencv는 0/255만 contour를 찾음)
        contours, _ = cv2.findContours(mask_uint8, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # 윤곽선 그리기
        cv2.drawContours(self.im, contours, -1, color, thickness)


    def draw_text(self, texts, colors):
        x_offset = 0
        y_offset = 35
        line_height = 20

        for i, (text, color) in enumerate(zip(texts, colors), start=1):
            y = y_offset + i * line_height
            cv2.putText(self.im, text, (x_offset, y), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
            
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
    def get_centers(xyxy: np.ndarray):
        xc = (xyxy[:, 0] + xyxy[:, 2]) / 2
        yc = (xyxy[:, 1] + xyxy[:, 3]) / 2
        return np.stack([xc, yc], axis=1).astype(np.float16)

    @staticmethod
    def get_center(xyxy: np.ndarray):
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

    def remove_contained(self, threshold: float = 0.8) -> 'Bboxes':
        keep_mask = self.get_containment_mask(self.xyxy, threshold)

        return Bboxes(
            self.xywhn[keep_mask],
            self.confs[keep_mask],
            self.class_ids[keep_mask],
            self.width,
            self.height
        )

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