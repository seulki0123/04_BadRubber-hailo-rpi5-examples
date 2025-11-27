# track_registry.py
from copy import deepcopy
from datetime import datetime, timedelta

class TrackRegistry:
    def __init__(self):
        self._tracks = {}  # track_id -> TrackState

    def add(self, track_state):
        self._tracks[track_state.track_id] = track_state

    def get(self, track_id):
        return self._tracks.get(int(track_id))

    def remove(self, track_id):
        return self._tracks.pop(int(track_id), None)

    def list_ids(self):
        return list(self._tracks.keys())

    def dump(self):
        return deepcopy({tid: t.to_dict() for tid, t in self._tracks.items()})