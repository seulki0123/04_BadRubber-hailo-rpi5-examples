# stream/domain/track_state.py
from math import sqrt
from datetime import datetime
from rubber_tracker.utils import generate_color

class TrackState:
    """
    Encapsulates per-track state and internal logic (speed calc, weigher enter/exit).
    """
    def __init__(self, track_id, ext_id, baler, input_zone, color=None):
        self.track_id = int(track_id)
        self.ext_id = ext_id
        self.baler = baler
        self.input_zone = input_zone
        self.color = color if color is not None else generate_color()

        # motion
        self.prev_center = None
        self.prev_time = None
        self.speed = 0.0

        # weigher
        self.weigher_zone = None
        self.weigher_entered = False
        self.weigher_exited = False

    # factory for convenience
    @classmethod
    def create(cls, track_id, ext_id, baler, input_zone, color=None):
        return cls(track_id=track_id, ext_id=ext_id, baler=baler, input_zone=input_zone, color=color)

    @property
    def info(self):
        return f"{self.track_id}/{self.ext_id}/{self.baler}/{self.input_zone}/{self.speed:.2f}"

    def to_dict(self):
        return {
            "track_id": self.track_id,
            "ext_id": self.ext_id,
            "baler": self.baler,
            "input_zone": self.input_zone,
            "color": self.color,
            "info": self.info,
        }

    # ------- motion/update -------
    def update_position(self, bbox):
        x1, y1, x2, y2 = bbox
        cx = (x1 + x2) / 2.0
        cy = (y1 + y2) / 2.0
        now = datetime.now()

        if self.prev_center is None:
            self.prev_center = (cx, cy)
            self.prev_time = now
            return

        px, py = self.prev_center
        dist = sqrt((cx - px) ** 2 + (cy - py) ** 2)
        dt = (now - self.prev_time).total_seconds()
        if dt > 0:
            self.speed = dist / dt

        self.prev_center = (cx, cy)
        self.prev_time = now

    # ------- weigher state -------
    def enter_weigher(self, weigher_zone):
        if self.weigher_entered:
            return None
        self.weigher_entered = True
        self.weigher_exited = False
        self.weigher_zone = weigher_zone
        # produce event payload (type weigher_in)
        return {
            "id": self.ext_id,
            "baler": self.baler,
            "zone": weigher_zone,
            "type": "weigher_in",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }

    def exit_weigher(self):
        if not self.weigher_entered or self.weigher_exited:
            return None
        out_zone = self.weigher_zone
        self.weigher_exited = True
        # reset weigher flag but keep weigher_zone for reporting
        self.weigher_zone = None
        return {
            "id": self.ext_id,
            "baler": self.baler,
            "zone": out_zone,
            "type": "weigher_out",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }
