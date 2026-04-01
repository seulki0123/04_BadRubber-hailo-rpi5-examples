class TrackEventHandler:
    def __init__(self, track_manager):
        self._track_manager = track_manager

    def on_created(self, track_id, bbox, conf):
        self._track_manager.on_created(track_id, bbox, conf)

    def on_updated(self, track_id, bbox, frame, age):
        self._track_manager.on_updated(track_id, bbox, frame, age)

    def on_removed(self, track_id, bbox, age):
        self._track_manager.on_removed(track_id, bbox, age)