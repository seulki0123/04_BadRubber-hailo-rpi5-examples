# track_state.py
from datetime import datetime
from rubber_tracker.utils import generate_color

class TrackState:
    def __init__(self, track_id, ext_id, baler, input_zone, color=None):
        self.track_id = int(track_id)
        self.ext_id = ext_id
        self.baler = baler
        self.input_zone = input_zone

        self.color = color if color is not None else generate_color()

        self.weigher_zone = None
        self.weigher_entered = False
        self.weigher_exited = False

    @property
    def info(self):
        return f"{self.track_id}/{self.ext_id}/{self.baler}/{self.input_zone}"

    def to_dict(self):
        return {
            "track_id": self.track_id,
            "ext_id": self.ext_id,
            "baler": self.baler,
            "input_zone": self.input_zone,
            "color": self.color,
            "info": self.info,
        }
