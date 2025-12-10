import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

from .utils import parse_detection
from rubber_tracker.utils import ModuleLogger, CustomThread

class DetectionProbe(ModuleLogger):
    def __init__(self):
        super().__init__(__class__.__name__)

    def __call__(self, pad, info, user_data):

        buffer = info.get_buffer()
        if buffer is None:
            return Gst.PadProbeReturn.OK

        frame, bboxes = parse_detection(pad, buffer)
        user_data.add(frame, bboxes)

        return Gst.PadProbeReturn.OK