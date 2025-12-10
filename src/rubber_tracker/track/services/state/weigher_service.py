from typing import List

from ...domain.track_state import TrackState

class WeigherService:
    """
    Detect entering/exiting weigher and build action payloads.
    """
    def __init__(self, delay):
        self.delay = delay

    def update(self, track: TrackState, weigher_zone) -> List[dict]:
        actions = []

        # entering
        if weigher_zone and not track.weigher_entered:
            track.enter_weigher(weigher_zone)
            actions.append({
                "event_type": "weigher_in",
                "zone": weigher_zone,
                "delay": self.delay,
            })

        # exiting
        if not weigher_zone and track.weigher_entered and not track.weigher_exited:
            # TODO: Decide whether to keep using `weigher_zone` as the exit parameter.
            prev_weigher_zone = track.weigher_zone
            track.exit_weigher()
            actions.append({
                "event_type": "weigher_out",
                "zone": prev_weigher_zone,
                "delay": self.delay,
            })

        return actions
