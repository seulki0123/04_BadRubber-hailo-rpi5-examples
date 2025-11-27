# track_state.py
from datetime import datetime
from rubber_tracker.utils import generate_color

class TrackState:
    def __init__(self, track_id, ext_id, baler, input_zone):
        self.track_id = int(track_id)
        self.ext_id = ext_id
        self.baler = baler
        self.input_zone = input_zone
        self.color = generate_color()
        self.measured = False
        self.weigher_zone = None
        self.info = f"{self.track_id}/{self.ext_id}/{self.baler}/{self.input_zone}"

    def mark_measured(self):
        self.measured = True

    def reset_measured(self):
        self.measured = False

    def to_dict(self):
        return {
            "track_id": self.track_id,
            "ext_id": self.ext_id,
            "baler": self.baler,
            "input_zone": self.input_zone,
            "color": self.color,
            "measured": self.measured,
            "info": self.info,
        }