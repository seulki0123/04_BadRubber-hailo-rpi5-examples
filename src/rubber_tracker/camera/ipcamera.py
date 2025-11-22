import time
import threading

import cv2
import yaml
import numpy as np
from gi.repository import Gst


from .utils import open_camera, resize_if_needed, safe_read, combine_frames, blank_frame
from rubber_tracker.utils import ModuleLogger, CustomThread
from rubber_tracker.utils import is_display_connected

class IPCamera(ModuleLogger):
    def __init__(self, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)["ipcamera"]

        self.url1, self.url2 = self._build_urls(config)

        self.cap1 = None
        self.cap2 = None
        self.fps = None
        self.format = "RGB"
        self.appsrc = None
        self.threads = []

        self.target_w = None
        self.target_h = None
        self.cfg_w = config["width"]
        self.cfg_h = config["height"]
        self.cfg_fps = config["fps"]
        self.video_sink = "autovideosink" if is_display_connected() else "fakesink"
        self.buf_dur = Gst.util_uint64_scale_int(1, Gst.SECOND, self.cfg_fps)
        self.thread_interval = config["thread_interval"]

        self.frame_count1 = 0
        self.frame_count2 = 0

        self.frame2_lock = threading.Lock()
        with self.frame2_lock:
            self.frame2 = blank_frame(self.cfg_w, self.cfg_h)

        self.stream_error = False
        
    def open_cameras(self):
        # open
        self.cap1, w1, h1, fps1 = open_camera(
            "IP Camera1", self.url1,
            self.log_info, self.log_warning, self.log_error,
            self.cfg_fps, self.cfg_w, self.cfg_h,
        )

        if self.url2:
            self.cap2, w2, h2, fps2 = open_camera(
                "IP Camera2", self.url2,
                self.log_info, self.log_warning, self.log_error,
                self.cfg_fps, self.cfg_w, self.cfg_h,
            )
        else:
            self.log_info("IP Camera2 disabled")

        # set
        self.target_w = self.cfg_w
        self.target_h = self.cfg_h if self.cap2 is None else self.cfg_h * 2
        self.fps = fps1

    def set_appsrc(self, pipeline):
        self.appsrc = pipeline.get_by_name("user_appsrc")
        if not self.appsrc:
            raise RuntimeError("appsrc not found in pipeline")

        self.appsrc.set_property("is-live", True)
        self.appsrc.set_property("format", Gst.Format.TIME)

        caps = (
            f"video/x-raw, format={self.format}, "
            f"width={self.target_w}, height={self.target_h}, "
            f"framerate={self.fps}/1, pixel-aspect-ratio=1/1"
        )
        self.appsrc.set_property("caps", Gst.Caps.from_string(caps))

        self.log_info(f"appsrc configured: {caps}, buf_dur={self.buf_dur}")

    def start_threads(self):
        # cam1
        cam1_thread = CustomThread(name=self.__class__.__name__ + "_cam1", task=self._task_cam1, interval=self.thread_interval)
        cam1_thread.start()
        self.threads.append(cam1_thread)

        # cam2
        if self.cap2:
            cam2_thread = CustomThread(name=self.__class__.__name__ + "_cam2", task=self._task_cam2, interval=self.thread_interval)
            cam2_thread.start()
            self.threads.append(cam2_thread)

    def get_stream_status(self):
        return not self.stream_error

    def _task_cam1(self):
        if not self.appsrc:
            raise RuntimeError("appsrc must be set before starting threads")

        # frame1
        frame1 = safe_read(self.cap1, self.fps, self.log_error, "CAM1")
        self.stream_error = False if frame1 is not None else True
        if self.stream_error: return
        frame1 = resize_if_needed(frame1, self.cfg_w, self.cfg_h)

        # merge frame1 and frame2
        with self.frame2_lock:
            frame = combine_frames(frame1, self.frame2, "vertical") if self.cap2 else frame1
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        # push buffer
        frame_bytes = frame.tobytes()
        buf = Gst.Buffer.new_allocate(None, len(frame_bytes), None)
        buf.fill(0, frame_bytes)
        buf.pts = self.frame_count1 * self.buf_dur
        buf.duration = self.buf_dur

        if self.appsrc.emit("push-buffer", buf) != Gst.FlowReturn.OK:
            self.log_error("push-buffer failed")
            return

        # update frame count
        self.frame_count1 += 1

    def _task_cam2(self):
        # read frame
        frame = safe_read(self.cap2, self.fps, self.log_error, "CAM2")
        self.stream_error = False if frame is not None else True
        if self.stream_error: return

        # resize frame
        with self.frame2_lock:
            self.frame2 = resize_if_needed(frame, self.cfg_w, self.cfg_h)

        # update frame count
        self.frame_count2 += 1

    def _build_urls(self, config):
        usr = config["usr"]
        pw = config["pw"]
        port = config["port"]
        channel = config["channel"]

        ip1 = config["ip1"]
        ip2 = config.get("ip2")

        url1 = f"rtsp://{usr}:{pw}@{ip1}:{port}/{channel}"
        url2 = f"rtsp://{usr}:{pw}@{ip2}:{port}/{channel}" if ip2 else None

        return url1, url2