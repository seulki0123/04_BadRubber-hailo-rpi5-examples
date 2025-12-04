# stream/services/track_controller.py
from typing import List

from ..domain.track_state import TrackState
from rubber_tracker.utils import ModuleLogger

class TrackController(ModuleLogger):
    """
    Responsible for creating/updating/removing tracks in the registry and handling weigher state changes.
    Returns a list of events (dictionaries) produced by actions.
    """
    def __init__(self, registry, fallback_service):
        super().__init__(self.__class__.__name__)
        self.registry = registry
        self.fallback = fallback_service

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
        Handle possible entering/exiting weigher. Returns list of event dicts:
        Each item: {"event": {...}, "delay": optional_seconds}
        """
        events = []
        # entering
        if weigher_zone and not track.weigher_entered:
            evt = track.enter_weigher(weigher_zone)
            if evt:
                events.append({"event": evt, "delay": track.weigher_delay})
        # exit
        if not weigher_zone and track.weigher_entered and not track.weigher_exited:
            evt = track.exit_weigher()
            if evt:
                events.append({"event": evt, "delay": track.weigher_delay})
        return events

    def remove_track(self, track_id):
        self.registry.remove(track_id)
        self.log_info(f"Track removed: {track_id}")
