from typing import List

from ...domain.track_state import TrackState

class WeigherService:
    """
    Detect entering/exiting weigher and build action payloads.
    """
    def __init__(self, delay):
        self.delay = delay

    def update(self, track: TrackState, zone) -> List[dict]:
        actions = []

        # entering
        if zone and not track.weigher_entered:
            track.enter_weigher(zone)
            actions.append({
                "event_type": "weigher_in",
                "zone": zone,
                "delay": self.delay,
            })

        # exiting
        if not zone and track.weigher_entered and not track.weigher_exited:
            prev_zone = track.weigher_zone
            track.exit_weigher()
            actions.append({
                "event_type": "weigher_out",
                "zone": prev_zone,
                "delay": self.delay,
            })

        return actions
