class OrchestratorEventHandler:
    def __init__(self, orchestrator):
        self._orchestrator = orchestrator

    def on_created(self, track_id, bbox):
        self._orchestrator.on_created(track_id, bbox)

    def on_updated(self, track_id, bbox, frame):
        self._orchestrator.on_updated(track_id, bbox, frame)

    def on_removed(self, track_id, bbox):
        self._orchestrator.on_removed(track_id, bbox)