from typing import NamedTuple
import numpy as np

class FramePacket(NamedTuple):
    source_id: str
    frame: np.ndarray
    timestamp: float