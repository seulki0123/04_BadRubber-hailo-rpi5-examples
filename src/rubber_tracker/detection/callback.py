import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst

from .utils import parse_detection
from rubber_tracker.utils import ModuleLogger, CustomThread
from rubber_tracker.processing import PostProcessorQueue, PostProcessor

class DetectionCallback(ModuleLogger):
    def __init__(self):
        super().__init__(__class__.__name__)

    def __call__(self, pad, info, user_data):
        
        buffer = info.get_buffer()
        if buffer is None:
            return Gst.PadProbeReturn.OK

        frame, bboxes, class_ids = parse_detection(pad, buffer)
        user_data.add(frame, bboxes, class_ids)

        return Gst.PadProbeReturn.OK

class UserData(PostProcessorQueue):   
    def __init__(self):
        super().__init__()
        self.threads = []
    
    def start_threads(self):
        # After Detection, Post Processing (With PostProcessorQueue)
        post_processor = PostProcessor(queue_getter=self.get)
        self._start_custom_thread(post_processor.name, post_processor.task, interval=post_processor.interval)

    def _start_custom_thread(self, name, task, interval):
        thread = CustomThread(name=name, task=task, interval=interval)
        thread.start()
        self.threads.append(thread)