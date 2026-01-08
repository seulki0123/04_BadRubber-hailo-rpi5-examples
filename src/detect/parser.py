from gi.repository import Gst
import numpy as np
import hailo

from .bboxes import Bboxes
from .frame import Frame

def get_xwyh_and_conf_from_buffer(buffer: Gst.Buffer) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
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


def parse_detection(pad: Gst.Pad, buffer: Gst.Buffer) -> tuple[Frame, Bboxes]:
    frame = Frame(pad, buffer)
    xywhn, confs, class_ids = get_xwyh_and_conf_from_buffer(buffer)
    bboxes = Bboxes(xywhn, confs, class_ids, frame.width, frame.height)
    return frame, bboxes