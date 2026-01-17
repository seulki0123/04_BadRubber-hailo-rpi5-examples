from gi.repository import Gst
import numpy as np
from typing import Any

from interfaces.video import VideoSource, FramePacket
from utils import load_config, ProcessLogger, CustomThread, Queue
from utils import float_to_fraction_str

from .hailo_apps_infra.detection_pipeline import GStreamerDetectionApp
from .parser import parse_detection
from .packet import DetectionPacket
from . import utils

class Detector(ProcessLogger):
    """
    NOTE:
    - buffer.pts is used only for timing (presentation timestamp).
    - buffer.offset is intentionally used as a custom frame ID.
      This is safe for this appsrc to inference-only pipeline.
      Do NOT use pts as a frame identifier.
    """

    def __init__(self):
        super().__init__(self.__class__.__name__)
        config = load_config()["detect"]

        # inputs
        self.video_sources: list[VideoSource]
        self.latest_frames: dict[str, np.ndarray] = {}
        self.width: int
        self.height: int
        self.merge_mode: str
        self.buf_duration: int
        self._set_inputs(
            sources=config["sources"],
            merge_mode=config["merge"]["mode"],
        )

        # detection pipeline
        self.detection_app: GStreamerDetectionApp
        self.appsrc: Gst.Element
        self._set_detection_pipeline(
            hef_path=config["hef_path"],
        )

        # worker thread
        self.queue: Queue[DetectionPacket] = Queue(name=self.__class__.__name__, max_size=config["queue_max_size"])
        self.thread = CustomThread(name=self.__class__.__name__, task=self._task, interval=0.0)
        self.frame_count: int = 0

    def get_results(self) -> DetectionPacket | None:
        return self.queue.get()

    def run(self) -> None:
        self.start()
        for video_source in self.video_sources:
            video_source.start()
        self.detection_app.run()
        
    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.thread.stop()
        for video_source in self.video_sources:
            video_source.stop()

    def _task(self) -> None:
        updated = False
        for video_source in self.video_sources:
            frame_packet: FramePacket | None = video_source.get_frame()
            if frame_packet is not None:
                self.latest_frames[frame_packet.source_id] = frame_packet.frame
                updated = True
        
        if not updated:
            return

        merged_frame = utils.merge_frames(
            frames=[self.latest_frames[src.id] for src in self.video_sources],
            merge_mode=self.merge_mode,
        )
        if not self._check_frame_size(merged_frame):
            return

        frame_bytes = merged_frame.tobytes()
        if not self._check_buffer_size(frame_bytes):
            return

        buf = Gst.Buffer.new_allocate(None, len(frame_bytes), None)
        buf.fill(0, frame_bytes)
        buf.pts = self.frame_count * self.buf_duration
        buf.duration = self.buf_duration
        buf.offset = self.frame_count # frame identifier (see class note)
        self.frame_count += 1

        if self.appsrc.emit("push-buffer", buf) != Gst.FlowReturn.OK:
            self.log_error("push-buffer failed")
            return

    def _set_inputs(self, sources: list[str], merge_mode: str) -> None:
        self.video_sources = []
        for source in sources:
            video_source = VideoSource(source)
            self.video_sources.append(video_source)
            self.latest_frames[video_source.id] = np.zeros(
                (video_source.height, video_source.width, 3),
                dtype=np.uint8,
            )
            self.log_info(f"Added video source: {video_source}")
        
        self.width, self.height = utils.get_video_size(
            self.video_sources,
            merge_mode=merge_mode,
        )

        self.merge_mode = merge_mode
        self.buf_duration = Gst.util_uint64_scale_int(1, Gst.SECOND, self.video_sources[0].fps)

    def _set_detection_pipeline(self, hef_path: str) -> None:
        # create detection app
        self.detection_app = GStreamerDetectionApp(
            video_source="user_appsrc",
            video_sink="fakesink",
            video_width=self.width,
            video_height=self.height,
            hef_path=hef_path,
            app_callback=self._detection_callback,
            user_data=None,
        )

        # add user appsrc to pipeline
        pipeline = self.detection_app.pipeline
        self.appsrc = pipeline.get_by_name("user_appsrc")
        if not self.appsrc:
            raise RuntimeError("user_appsrc not found in pipeline")

        self.appsrc.set_property("is-live", True)
        self.appsrc.set_property("format", Gst.Format.TIME)

        video_infos = utils.get_video_infos(self.video_sources)
        caps_string = (
            f"video/x-raw, format={video_infos['format']}, "
            f"width={self.width}, height={self.height}, "
            f"framerate={float_to_fraction_str(video_infos['fps'])}, pixel-aspect-ratio=1/1"
        )
        
        caps = Gst.Caps.from_string(caps_string)
        self.appsrc.set_property("caps", caps)
        
        pipeline_string = self.detection_app.get_pipeline_string()
        self.log_info(f"Detection App Pipeline: {pipeline_string}")
        
    def _detection_callback(self, pad: Gst.Pad, info: Gst.PadProbeInfo, user_data: Any) -> Gst.PadProbeReturn:
        buffer = info.get_buffer()
        if buffer is None:
            return Gst.PadProbeReturn.DROP

        frame, bboxes = parse_detection(pad, buffer)
        frame_id = buffer.offset

        detection_packet = DetectionPacket(
            frame_id=frame_id,
            frame=frame,
            bboxes=bboxes,
        )
        self.queue.add(detection_packet)

        return Gst.PadProbeReturn.OK

    def _check_frame_size(self, frame: np.ndarray) -> bool:
        actual_height, actual_width = frame.shape[:2]
        if actual_width != self.width or actual_height != self.height:
            self.log_error(
                f"Frame size mismatch: expected {self.width}x{self.height}, "
                f"got {actual_width}x{actual_height}"
            )
            return False
        return True
    
    def _check_buffer_size(self, frame_bytes: bytes) -> bool:
        expected_size = self.width * self.height * 3  # RGB
        if len(frame_bytes) != expected_size:
            self.log_error(
                f"Buffer size mismatch: expected {expected_size}, "
                f"got {len(frame_bytes)}"
            )
            return False
        return True