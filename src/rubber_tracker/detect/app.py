from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp
from .probe import DetectionProbe
from .buffer import DetectionBuffer
from .pipeline import DetectionPipeline

class DetectionApp(GStreamerDetectionApp):
    def __init__(self):
        self.gstream_pipeline = None
        self.post_process_pipeline = None

    def create_pipeline(self, width, height, video_sink, event_handler, draw_callback):
        callback = DetectionProbe()
        buffer = DetectionBuffer()
        self.gstream_pipeline = GStreamerDetectionApp(callback, buffer, width, height, video_sink)
        self.post_process_pipeline = DetectionPipeline(buffer.get, event_handler, draw_callback)

    def run(self):
        self.post_process_pipeline.run()
        self.gstream_pipeline.run() # must last

    def get_gst_pipeline(self):
        return self.gstream_pipeline.pipeline