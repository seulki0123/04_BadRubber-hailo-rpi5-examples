import threading
from typing import Dict, Optional
from types import MappingProxyType
from .track_state import TrackState

class TrackRegistry:
    def __init__(self):
        self._tracks: Dict[int, TrackState] = {}
        self._lock = threading.RLock()

    def add(self, track: TrackState):
        with self._lock:
            self._tracks[track.track_id] = track

    def get(self, track_id: int) -> Optional[TrackState]:
        with self._lock:
            return self._tracks.get(track_id)

    def remove(self, track_id: int):
        with self._lock:
            self._tracks.pop(track_id, None)

    def dump_subset(self, track_ids):
        with self._lock:
            return {tid: self._tracks.get(tid) for tid in track_ids}

    def get_map(self):
        """
        Return SAFE reference for read-only real-time track lookup.
        BalerService는 callback thread에서 read-only로 사용하므로 OK.
        """
        return MappingProxyType(self._tracks)