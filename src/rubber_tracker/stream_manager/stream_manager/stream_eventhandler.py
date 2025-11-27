class StreamEventHandler:
    def __init__(self, stream_manager):
        self._sm = stream_manager

    def on_created(self, track):
        self._sm.on_created(track)

    def on_updated(self, track):
        self._sm.on_updated(track)

    def on_removed(self, track):
        self._sm.on_removed(track)

    def on_updated(self, track, weight):
        self._sm.on_updated(track, weight)