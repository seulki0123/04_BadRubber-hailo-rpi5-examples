from typing import Any

from .frame_store import FrameStore


class ImageEventCapture:
    def __init__(self, inner_handler: Any, frame_store: FrameStore):
        if inner_handler is None:
            raise ValueError("inner_handler must not be None")
        if frame_store is None:
            raise ValueError("frame_store must not be None")
        self._inner = inner_handler
        self._frames = frame_store

    def on_created(self, track_id, bbox, conf):
        self._frames.update(track_id, bbox)
        self._inner.on_created(track_id, bbox, conf)

    def on_updated(self, track_id, bbox, frame, age):
        self._frames.update(track_id, bbox, frame, age)
        self._inner.on_updated(track_id, bbox, frame, age)

    def on_removed(self, track_id, bbox, age):
        self._inner.on_removed(track_id, bbox, age)
        self._frames.remove(track_id)
