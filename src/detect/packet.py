from typing import NamedTuple

from .frame import Frame
from .bboxes import Bboxes

class DetectionPacket(NamedTuple):
    frame_id: int
    frame: Frame
    bboxes: Bboxes