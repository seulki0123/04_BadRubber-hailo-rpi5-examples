import cv2
import hailo
import numpy as np

from hailo_apps_infra.hailo_rpi_common import (
    get_caps_from_pad,
    get_numpy_from_buffer,
)

class Frame:
    def __init__(self, pad, buffer):
        caps = get_caps_from_pad(pad)
        self.format = caps[0]
        self.width = caps[1]
        self.height = caps[2]
        self.im0 = self.get_frame(buffer) # original image
        self.im = self.im0.copy()

    def get_frame(self, buffer):
        frame = get_numpy_from_buffer(buffer, self.format, self.width, self.height)
        return cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)

    def draw(self, bboxes, confs, labels, track_ids):
        for bbox, conf, label, track_id in zip(bboxes, confs, labels, track_ids):
            x1, y1, x2, y2 = map(int, bbox)
            color = (0, 0, 255) if label == 1 else (0, 255, 0)
            cv2.rectangle(self.im, (x1, y1), (x2, y2), color, 2)
            cv2.putText(self.im, f"ID: {track_id} {label} {conf}", (x1, y1+30), cv2.FONT_HERSHEY_SIMPLEX, 1, color, 2)


class Bboxes:
    def __init__(self, xywhn, confs, width, height):
        self.width = width
        self.height = height
        self.xywhn = xywhn
        self.confs = confs
        self.xyxy = self.xywhn2xyxy(xywhn, width, height) if xywhn.shape[0] > 0 else None

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


def get_xwyh_and_conf_from_buffer(buffer):
    roi = hailo.get_roi_from_buffer(buffer)
    detections = roi.get_objects_typed(hailo.HAILO_DETECTION)

    xywh_norms = []
    confidences = []
    for detection in detections:
        # xywh_norms
        bbox = detection.get_bbox()
        xyxy = bbox.xmin(), bbox.ymin(), bbox.xmax(), bbox.ymax()
        xywh_norms.append(Bboxes.xyxy2xywh(xyxy))
        # confidences
        confidence = detection.get_confidence()
        confidences.append(round(confidence, 4))

    # 리스트 → NumPy 배열로 변환
    xywh_norms = np.array(np.array(xywh_norms), dtype=np.float32)
    confidences = np.array(confidences, dtype=np.float32)

    return xywh_norms, confidences


def parse_detection(pad, buffer):
    frame = Frame(pad, buffer)
    xywhn, confs = get_xwyh_and_conf_from_buffer(buffer)
    bboxes = Bboxes(xywhn, confs, frame.width, frame.height)
    return frame, bboxes