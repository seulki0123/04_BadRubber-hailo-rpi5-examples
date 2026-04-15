from ...domain.track_state import TrackState
from rubber_tracker.utils import ProcessLogger

class TrackController(ProcessLogger):

    def __init__(
        self,
        registry,
        fallback_service,
        weigher_service,
        baler_service,
        unsynced_baler,
    ):
        super().__init__(self.__class__.__name__)
        self.registry = registry
        self.fallback = fallback_service
        self.weigher_service = weigher_service
        self.baler_service = baler_service
        self.unsynced_baler = unsynced_baler
        
    # -------- create / remove --------
    def create_track(self, track_id, input_zone, data, fallback_case, bbox, conf):
        if data is None:
            fb_baler, fb_id = self.fallback.get_fallback_id(fallback_case)
            track = TrackState(track_id, fb_id, fb_baler, input_zone, synced=False, unsynced_baler=self.unsynced_baler, color=(0,0,0), created_bbox=bbox, created_conf=conf)
            self.log_warning(f"Fallback track created: {fb_id} at {input_zone}")
        else:
            track = TrackState(track_id, data['id'], data['input_baler'], input_zone, synced=data['synced'], unsynced_baler=self.unsynced_baler, created_bbox=bbox, created_conf=conf)
            self.log_info(f"Track created: {track.info}")

        self.registry.add(track)
        return track

    def remove_track(self, track_id):
        try:
            self.baler_service.on_track_removed(track_id)
        except Exception as e:
            self.log_error(f"Error in baler on_track_removed for {track_id}: {e}", exc_info=True)
        self.registry.remove(track_id)
        self.log_info(f"Track removed: {track_id}")

    # -------- per frame update --------
    def update_track(self, track, bbox, frame, weigher_zone, classify_zone):
        weigher_actions = self.weigher_service.update(track, weigher_zone)
        baler_actions = self.baler_service.update(track, bbox, frame, classify_zone)

        return weigher_actions