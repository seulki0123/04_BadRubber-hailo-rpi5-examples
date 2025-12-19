from ...domain.track_state import TrackState
from rubber_tracker.utils import ProcessLogger

class TrackController(ProcessLogger):

    def __init__(
        self,
        registry,
        fallback_service,
        weigher_service,
        baler_service,
        create_fallback_baler,
        classify_fallback_baler,
        unsynced_baler,
    ):
        super().__init__(self.__class__.__name__)
        self.registry = registry
        self.fallback = fallback_service
        self.weigher_service = weigher_service
        self.baler_service = baler_service
        self.create_fallback_baler = create_fallback_baler
        self.unsynced_baler = unsynced_baler
        
    # -------- create / remove --------
    def create_track(self, track_id, input_zone, data):
        if data is None:
            fb = self.fallback.get_fallback_id(2)
            track = TrackState(track_id, fb, self.create_fallback_baler, input_zone, synced=False, unsynced_baler=self.unsynced_baler, color=(0,0,0))
            self.log_warning(f"Fallback track created: {fb} at {input_zone}")
        else:
            track = TrackState(track_id, data['id'], data['input_baler'], input_zone, synced=data['synced'], unsynced_baler=self.unsynced_baler)
            self.log_info(f"Track created: {track.info}")

        self.registry.add(track)
        return track

    def remove_track(self, track_id):
        self.baler_service.on_track_removed(track_id)
        self.registry.remove(track_id)
        self.log_info(f"Track removed: {track_id}")

    # -------- per frame update --------
    def update_track(self, track, bbox, frame, weigher_zone, classify_zone):
        weigher_actions = self.weigher_service.update(track, weigher_zone)
        baler_actions = self.baler_service.update(track, bbox, frame, classify_zone)

        return weigher_actions