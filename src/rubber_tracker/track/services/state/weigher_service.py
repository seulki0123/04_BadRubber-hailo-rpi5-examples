from typing import List

from ...domain.track_state import TrackState

class WeigherService:
    """
    Detect entering/exiting weigher and build action payloads.
    """
    def __init__(self, delay, zone_map):
        self.delay = delay
        self.zone_map = zone_map

    def update(self, track: TrackState, weigher_zone) -> List[dict]:
        actions = []

        # entering
        if weigher_zone and not track.weigher_entered:
            track.enter_weigher(weigher_zone)
            actions.append({
                "event_type": "weigher_in",
                "zone": self.zone_map[weigher_zone].get('in'),
                "delay": self.delay,
            })

        # exiting
        if not weigher_zone and track.weigher_entered and not track.weigher_exited:
            # TODO: Decide whether to keep using `weigher_zone` as the exit parameter.
            prev_weigher_zone = track.weigher_zone
            track.exit_weigher()
            actions.append({
                "event_type": "weigher_out",
                "zone": self.zone_map[prev_weigher_zone].get('out'),
                "delay": self.delay,
            })

        return actions
