from ...domain.track_state import TrackState

class BalerService:
    """
    Updates track's motion, speed, and baler_active state.
    """
    def __init__(self, speed_service, classify_service, capture_service):
        self.speed_service = speed_service
        self.classify_service = classify_service
        self.capture_service = capture_service

    def update(self, track: TrackState, bbox, frame, classify_zone):
        actions = []
        self._update_position(track, bbox)

        if classify_zone is None:
            self._set_text_color(track, classify_activated=False)
            return actions

        if self._is_ready_for_classification(track):
            crop = self.capture_service.crop(bbox, frame, save_folder=f"{classify_zone}_{str(track.track_id).zfill(6)}", save_infos=[track.speed])
            baler = self.classify_service.process(crop)
            self._update_baler(track, baler)
        else:
            baler = None

        if self._is_fully_stopped(track) and track.final_baler is None:
            self._update_final_baler(track)
            actions.append({
                "event_type": "final_baler",
                "zone": classify_zone,
                "delay": 0,
            })
        
        return actions

    def _update_position(self, track: TrackState, bbox):
        track.update_position(bbox)

    def _update_baler(self, track: TrackState, baler):
        track.update_baler(baler)
        self._set_text_color(track, classify_activated=True)

    def _update_final_baler(self, track: TrackState):
        track.update_final_baler()
        self._set_text_color(track, classify_activated=False)

    def _set_text_color(self, track: TrackState, classify_activated: bool):
        color = (0, 255, 0) if classify_activated is True else None
        track.set_text_color(color)

    def _is_ready_for_classification(self, track: TrackState):
        return track.final_baler is None and self.speed_service.is_slow(track.speed)
    
    def _is_fully_stopped(self, track: TrackState):
        return track.final_baler is None and self.speed_service.is_stop(track.speed)