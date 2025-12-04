# stream/services/event_service.py
from datetime import datetime

class EventService:
    """
    Builds event payloads and routes messages into EventMessage system.
    """
    def __init__(self, event_messages):
        self.event_messages = event_messages

    def build_event(self, track, zone, event_type="created", rejected=False):
        evt = {
            'id': track.ext_id,
            'baler': track.baler,
            'zone': zone,
            'rejected': rejected,
            'type': event_type,
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }
        # if we want to log/display internal messages:
        if event_type == "created":
            self.event_messages.add(f"□■■■ Track Created: '{track.info}'", track.color)
        elif event_type == "weigher_in":
            self.event_messages.add(f"■□■■ Track Weighed: '{track.info}' in '{zone}'", track.color)
        elif event_type == "weigher_out":
            self.event_messages.add(f"■■□■ Track Weighed Reset: '{track.info}' in '{zone}'", track.color)
        elif event_type == "removed":
            pass
        return evt
