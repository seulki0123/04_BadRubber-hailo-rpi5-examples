import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib
import os
import multiprocessing
import numpy as np
import setproctitle
import cv2
import time
import hailo
from .hailo_rpi_common import (
    detect_hailo_arch,
)
from .gstreamer_helper_pipelines import(
    QUEUE,
    SOURCE_PIPELINE,
    INFERENCE_PIPELINE,
    INFERENCE_PIPELINE_WRAPPER,
    TRACKER_PIPELINE,
    USER_CALLBACK_PIPELINE,
    DISPLAY_PIPELINE,
)
from .gstreamer_app import GStreamerApp
from .utils import app_callback_class, dummy_callback

class GStreamerDetectionApp(GStreamerApp):
    def __init__(
        self,
        video_source,
        video_sink,
        video_width,
        video_height,
        hef_path,
        app_callback,
        user_data,
        batch_size=2,
        nms_score_threshold=0.3,
        nms_iou_threshold=0.45,
        post_process_so_path='venv_syspkg/lib/python3.11/site-packages/resources/libyolo_hailortpp_postprocess.so',
        post_function_name='filter_letterbox',
        labels_json=None,
    ):

        super().__init__(
            user_data=user_data,
            video_source=video_source,
            video_sink=video_sink,
            video_width=video_width,
            video_height=video_height,
        )

        # Set Hailo parameters these parameters should be set based on the model used
        self.batch_size = batch_size
        self.nms_score_threshold = nms_score_threshold
        self.nms_iou_threshold = nms_iou_threshold

        self.arch = detect_hailo_arch()
        self.hef_path = hef_path

        # Set the post-processing shared object file
        self.post_process_so = os.path.join(post_process_so_path)
        self.post_function_name = post_function_name
        
        # User-defined label JSON file
        self.labels_json = labels_json
        self.app_callback = app_callback

        self.thresholds_str = (
            f"nms-score-threshold={self.nms_score_threshold} "
            f"nms-iou-threshold={self.nms_iou_threshold} "
            f"output-format-type=HAILO_FORMAT_TYPE_FLOAT32"
        )

        self.create_pipeline()

    def get_pipeline_string(self):
        source_pipeline = SOURCE_PIPELINE(self.video_source, self.video_width, self.video_height)
        detection_pipeline = INFERENCE_PIPELINE(
            hef_path=self.hef_path,
            post_process_so=self.post_process_so,
            post_function_name=self.post_function_name,
            batch_size=self.batch_size,
            config_json=self.labels_json,
            additional_params=self.thresholds_str)
        detection_pipeline_wrapper = INFERENCE_PIPELINE_WRAPPER(detection_pipeline)
        tracker_pipeline = TRACKER_PIPELINE(class_id=1)
        user_callback_pipeline = USER_CALLBACK_PIPELINE()
        display_pipeline = DISPLAY_PIPELINE(video_sink=self.video_sink, sync=self.sync, show_fps=self.show_fps)

        pipeline_string = (
            f'{source_pipeline} ! '
            f'{detection_pipeline_wrapper} ! '
            f'{tracker_pipeline} ! '
            f'{user_callback_pipeline} ! '
            f'{display_pipeline}'
        )
        print(pipeline_string)
        return pipeline_string

if __name__ == "__main__":
    # Create an instance of the user app callback class
    user_data = app_callback_class()
    app_callback = dummy_callback
    hef_path = "yolov8n.hef"
    app = GStreamerDetectionApp(hef_path, app_callback, user_data)
    app.run()
