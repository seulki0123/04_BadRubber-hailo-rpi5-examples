from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp
from .probe import DetectionProbe
from .buffer import DetectionBuffer
from rubber_tracker.utils import load_config, is_display_connected

class DetectionApp(GStreamerDetectionApp):
    def __init__(self):
        config = load_config()
        self.hef_path = config["detect"]["weight"]
        self.video_source = config["detect"]["video_source"]
        self.video_sink = "autovideosink" if is_display_connected() else "fakesink"
        self.gstream_pipeline = None
        self.post_process_pipeline = None

    def create_pipeline(self, width, height, video_sink):
        callback = DetectionProbe()
        buffer = DetectionBuffer()
        self.gstream_pipeline = GStreamerDetectionApp(
            video_source=self.video_source,
            video_sink=self.video_sink,
            video_width=width,
            video_height=height,
            hef_path=self.hef_path,
            app_callback=callback,
            user_data=buffer,
        )

    def run(self):
        self.gstream_pipeline.run() # must last

    def get_gst_pipeline(self):
        return self.gstream_pipeline.pipeline