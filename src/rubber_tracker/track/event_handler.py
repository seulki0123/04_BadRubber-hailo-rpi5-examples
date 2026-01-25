class TrackEventHandler:
    def __init__(self, track_manager):
        self._track_manager = track_manager

    def on_created(self, track_id, bbox):
        self._track_manager.on_created(track_id, bbox)

    def on_updated(self, track_id, bbox, frame):
        self._track_manager.on_updated(track_id, bbox, frame)

    def on_removed(self, track_id, bbox, age):
        self._track_manager.on_removed(track_id, bbox, age)