from ...domain.track_state import TrackState

class BalerService:
    """
    Updates track's motion, speed, and baler_active state.
    """
    def __init__(self, speed_service, classify_service, capture_service):
        self.speed_service = speed_service
        self.classify_service = classify_service
        self.capture_service = capture_service

    def update(self, track: TrackState, bbox, frame, weigher_zone):
        actions = []
        self._update_position(track, bbox)

        if weigher_zone is None:
            return actions

        if self._is_ready_for_classification(track):
            crop = self.capture_service.crop(bbox, frame, save_folder=f"{weigher_zone}_{str(track.track_id).zfill(6)}", save_infos=[track.speed])
            baler = self.classify_service.process(crop)
            self._update_baler(track, baler)
        else:
            baler = None

        if self._is_fully_stopped(track) and track.final_baler is None:
            track.update_final_baler()
            actions.append({
                "event_type": "final_baler",
                "zone": weigher_zone,
                "delay": 0,
            })
        
        return actions

    def _update_position(self, track: TrackState, bbox):
        track.update_position(bbox)

    def _update_baler(self, track: TrackState, baler):
        track.update_baler(baler)

    def _is_ready_for_classification(self, track: TrackState):
        return track.weigher_zone is not None and self.speed_service.is_slow(track.speed)
    
    def _is_fully_stopped(self, track: TrackState):
        return track.weigher_zone is not None and self.speed_service.is_stop(track.speed)