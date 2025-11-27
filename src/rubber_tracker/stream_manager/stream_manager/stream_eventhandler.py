class StreamEventHandler:
    def __init__(self, stream_manager):
        self._sm = stream_manager

    def on_created(self, track_id, bbox):
        self._sm.on_created(track_id, bbox)

    def on_updated(self, track_id, bbox):
        self._sm.on_updated(track_id, bbox)

    def on_removed(self, track_id, bbox):
        self._sm.on_removed(track_id, bbox)

    def on_updated(self, track_id, bbox):
        self._sm.on_updated(track_id, bbox)