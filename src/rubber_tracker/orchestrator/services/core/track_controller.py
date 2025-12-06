from ...domain.track_state import TrackState
from rubber_tracker.utils import ModuleLogger

class TrackController(ModuleLogger):

    def __init__(
        self,
        registry,
        fallback_service,
        weigher_service,
        baler_service
    ):
        super().__init__(self.__class__.__name__)
        self.registry = registry
        self.fallback = fallback_service
        self.weigher_service = weigher_service
        self.baler_service = baler_service

    # -------- create / remove --------
    def create_track(self, track_id, input_zone, data):
        if data is None:
            fb = self.fallback.get_fallback_id(2)
            track = TrackState(track_id, fb, "10", input_zone, color=(0,0,0))
            self.log_warning(f"Fallback track created: {fb} at {input_zone}")
        else:
            track = TrackState(track_id, data['id'], data['baler'], input_zone)
            self.log_info(f"Track created: {track.info}")

        self.registry.add(track)
        return track

    def remove_track(self, track_id):
        self.registry.remove(track_id)
        self.log_info(f"Track removed: {track_id}")

    # -------- per frame update --------
    def update_track(self, track, bbox, frame, weigher_zone):
        weigher_actions = self.weigher_service.update(track, weigher_zone)
        baler_actions = self.baler_service.update(track, bbox, frame, weigher_zone)

        return weigher_actions