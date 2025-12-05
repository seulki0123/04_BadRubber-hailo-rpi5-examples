from ...domain.track_state import TrackState

class TrackStateService:
    """
    Updates track's motion, speed, and baler_active state.
    """
    def __init__(self, speed_service):
        self.speed_service = speed_service

    def update(self, track: TrackState, bbox, weigher_zone):
        # position → speed 업데이트
        track.update_position(bbox)

        # baler active/inactive 판단
        if weigher_zone and self.speed_service.is_slow(track.speed):
            track.set_baler_active()
        else:
            track.set_baler_inactive()
