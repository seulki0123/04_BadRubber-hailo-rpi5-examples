import cv2
import numpy as np
from gi.repository import Gst

from .hailo_apps_infra.hailo_rpi_common import get_numpy_from_buffer, get_caps_from_pad

class Frame:
    def __init__(self, pad: Gst.Pad, buffer: Gst.Buffer) -> None:
        caps = get_caps_from_pad(pad)

        self.format: str = caps[0]
        self.width: int = caps[1]
        self.height: int = caps[2]
        
        self.im0: np.ndarray = self._get_frame(buffer) # original image
        self.im: np.ndarray = self.im0.copy()

    def _get_frame(self, buffer: Gst.Buffer) -> np.ndarray:
        return get_numpy_from_buffer(buffer, self.format, self.width, self.height)