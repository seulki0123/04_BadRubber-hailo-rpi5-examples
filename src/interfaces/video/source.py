import time

import cv2

from utils import load_config, Queue, ProcessLogger, CustomThread
from .packet import FramePacket

class VideoSource(ProcessLogger):
    def __init__(self, source_id: str):
        name = f"{self.__class__.__name__}_{source_id}"
        super().__init__(name)
        cfg = load_config()["video_source"]

        self.id: str
        self.type: str
        self.url: str
        self.width: int
        self.height: int
        self.fps: float
        self.format: str
        self.thread_interval: float
        self.cap: cv2.VideoCapture | None = None

        self._set_source(cfg, source_id)
        self._open()

        self.queue: Queue[FramePacket] = Queue(name=name, max_size=1)
        self.thread = CustomThread(name=name, task=self._task, interval=self.thread_interval)

    def start(self) -> None:
        self.thread.start()

    def stop(self) -> None:
        self.thread.stop()
        if self.cap:
            self.cap.release()

    def get_frame(self) -> FramePacket | None:
        return self.queue.get()

    def _task(self) -> None:
        if not self.cap or not self.cap.isOpened():
            self._reopen()
            return

        ret, frame = self.cap.read()
        if not ret or frame is None:
            self.log_warning("Failed to read frame")
            self._reopen()
            return

        self.queue.add(FramePacket(
            source_id=self.id,
            frame=frame,
            timestamp=time.time()
        ))

    def _set_source(self, cfg: dict, source_id: str) -> None:
        defaults = cfg["defaults"]
        sources = cfg["sources"]

        source = next((s for s in sources if s["id"] == source_id), None)
        if source is None:
            raise ValueError(f"Source '{source_id}' not found")

        # merge defaults + source (source overrides defaults)
        merged = defaults.copy()
        merged.update(source)

        self.id = merged["id"]
        self.type = merged["type"]
        self.url = merged["url"]
        self.width = merged["width"]
        self.height = merged["height"]
        self.fps = merged["fps"]
        self.format = merged["format"]
        self.thread_interval = merged["thread_interval"]

    def _open(self) -> None:
        self.log_info(f"Opening video source: {self.url}")
        self.cap = cv2.VideoCapture(self.url)

        if not self.cap.isOpened():
            self.cap = None
            raise RuntimeError(f"Failed to open video source: {self.url}")

        self._validate_stream()

    def _reopen(self) -> None:
        self.log_warning("Reopening video source")
        if self.cap:
            self.cap.release()
        time.sleep(1.0)
        self._open()

    def _validate_stream(self) -> None:
        actual_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        actual_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        actual_fps = self.cap.get(cv2.CAP_PROP_FPS)

        if actual_width != self.width:
            raise RuntimeError(
                f"Width mismatch: config={self.width}, actual={actual_width}"
            )

        if actual_height != self.height:
            raise RuntimeError(
                f"Height mismatch: config={self.height}, actual={actual_height}"
            )

        if abs(actual_fps - self.fps) > 1.0:
            raise RuntimeError(
                f"FPS mismatch: config={self.fps}, actual={actual_fps}"
            )

        self.log_info(
            f"Video source validated: "
            f"{actual_width}x{actual_height}@{actual_fps:.2f}"
        )


    def __repr__(self) -> str:
        return (
            f"VideoSource(id={self.id}, type={self.type}, "
            f"{self.width}x{self.height}@{self.fps}, format={self.format})"
        )