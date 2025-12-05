# stream/services/event_service.py
from datetime import datetime
from rubber_tracker.utils import ModuleLogger

class EventService(ModuleLogger):
    """
    Builds event payloads and routes messages into EventMessage system.
    """
    def __init__(self, event_messages):
        super().__init__(self.__class__.__name__)
        self.event_messages = event_messages

    def build_event(self, track, zone, event_type="created", rejected=False):
        evt = {
            'id': track['ext_id'],
            'baler': track['baler'],
            'zone': zone,
            'rejected': rejected,
            'type': event_type,
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }
        # if we want to log/display internal messages:
        if event_type == "created":
            msg = f"□■■■ Track Created: '{track['info']}'"
        elif event_type == "weigher_in":
            msg = f"■□■■ Track Weighed: '{track['info']}' in '{zone}'"
        elif event_type == "weigher_out":
            msg = f"■■□■ Track Weighed Reset: '{track['info']}' in '{zone}'"
        elif event_type == "exited":
            msg = f"■■■□ Track Exited: '{track['info']}' → '{zone}'"
        elif event_type == "removed":
            msg = f"■■■■ Track Removed: '{track['info']}'"
        else:
            self.log_error(f"Unknown event type: {event_type}")
            return None
        self.log_info(msg)
        self.event_messages.add(msg, track['color'])
        return evt