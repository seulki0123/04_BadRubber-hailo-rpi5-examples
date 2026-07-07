import threading
from collections import deque
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import numpy as np


def _as_int(value, default=None):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


class FrameStore:
    def __init__(self, buffer_size: int = 30) -> None:
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._tracks: Dict[int, Dict[str, Any]] = {}
        self._seq = 0
        self._buffer = deque(maxlen=max(1, int(buffer_size)))

    def set_buffer_size(self, buffer_size: int) -> None:
        size = max(1, int(buffer_size))
        with self._lock:
            self._buffer = deque(list(self._buffer)[-size:], maxlen=size)

    def update(self, track_id, bbox, frame=None, age: int = 0) -> None:
        tid = _as_int(track_id)
        if tid is None:
            return

        with self._lock:
            if frame is not None:
                self._frame = frame
                self._seq += 1

            self._tracks[tid] = {
                "bbox": tuple(bbox) if bbox is not None else None,
                "age": _as_int(age, 0),
            }

            if frame is not None:
                self._buffer.append({
                    "seq": self._seq,
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                    "frame": frame.copy(),
                    "tracks": self._copy_tracks(),
                })

    def remove(self, track_id) -> None:
        tid = _as_int(track_id)
        if tid is not None:
            with self._lock:
                self._tracks.pop(tid, None)

    def snapshot(self) -> Tuple[Optional[np.ndarray], Dict[int, Dict[str, Any]]]:
        with self._lock:
            frame, tracks = self._frame, self._copy_tracks()
        return (frame.copy() if frame is not None else None), tracks

    def current_seq(self) -> int:
        with self._lock:
            return self._seq

    def frames_between(self, start_seq: int, end_seq: int) -> List[Dict[str, Any]]:
        with self._lock:
            items = [x for x in self._buffer if start_seq <= x["seq"] <= end_seq]
        return [
            {**item, "frame": item["frame"].copy(), "tracks": {k: dict(v) for k, v in item["tracks"].items()}}
            for item in items
        ]

    def get_bbox(self, track_id) -> Optional[Tuple[int, int, int, int]]:
        tid = _as_int(track_id)
        with self._lock:
            item = self._tracks.get(tid)
            return item["bbox"] if item else None

    def size(self) -> int:
        with self._lock:
            return len(self._tracks)

    def _copy_tracks(self) -> Dict[int, Dict[str, Any]]:
        return {k: dict(v) for k, v in self._tracks.items()}
