# stream/services/track_controller.py
from typing import List

from ..domain.track_state import TrackState
from rubber_tracker.utils import ModuleLogger

class TrackController(ModuleLogger):
    """
    Responsible for creating/updating/removing tracks in the registry and handling weigher state changes.
    Returns a list of events (dictionaries) produced by actions.
    """
    def __init__(self, registry, fallback_service, weigher_delay=0):
        super().__init__(self.__class__.__name__)
        self.registry = registry
        self.fallback = fallback_service
        self.weigher_delay = weigher_delay
        
    def create_track(self, track_id, input_zone, data) -> TrackState:
        if data is None:
            # create fallback track
            fallback_id = self.fallback.get_fallback_id(2)
            track = TrackState(track_id=track_id, ext_id=fallback_id, baler="10", input_zone=input_zone, color=(0,0,0))
            self.log_warning(f"Fallback track created: {fallback_id} at {input_zone}")
        else:
            track = TrackState(track_id=track_id, ext_id=data['id'], baler=data['baler'], input_zone=input_zone)
            self.log_info(f"Track created: {track.info}")
        self.registry.add(track)
        return track

    def process_weigher(self, track: TrackState, weigher_zone) -> List[dict]:
        """
        Detect entering/exiting weigher.
        Returns a list of actions:
        Each: {"event_type": "...", "zone": "...", "delay": seconds}
        """
        actions = []

        # --- entering ---
        if weigher_zone and not track.weigher_entered:
            track.enter_weigher(weigher_zone)
            actions.append({
                "event_type": "weigher_in",
                "zone": weigher_zone,
                "delay": self.weigher_delay,
            })

        # --- exiting ---
        if not weigher_zone and track.weigher_entered and not track.weigher_exited:
            zone = track.weigher_zone  # exit 할 때 기존 zone 필요
            track.exit_weigher()
            actions.append({
                "event_type": "weigher_out",
                "zone": zone,
                "delay": self.weigher_delay,
            })

        return actions

    def remove_track(self, track_id):
        self.registry.remove(track_id)
        self.log_info(f"Track removed: {track_id}")
