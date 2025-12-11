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
            'id': track.get('id'),
            'input_baler': track.get('input_baler') if 'input_baler' in track else track.get('baler'),
            'final_baler': track.get('final_baler'),
            'baler': 10,
            'zone': zone,
            'rejected': rejected,
            'type': event_type + "_" + zone if zone else event_type,
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }
        # if we want to log/display internal messages:
        if event_type == "id_added":
            msg = f"□□□□ External ID Added: '{track.get('id')}' in '{zone}'"
        elif event_type == "created":
            msg = f"□■■■ Track Created: '{track.get('info')}'"
        elif event_type == "weigher_in":
            msg = f"■□■■ Track Weighed: '{track.get('info')}' in '{zone}'"
        elif event_type == "weigher_out":
            msg = f"■■□■ Track Weighed Reset: '{track.get('info')}' in '{zone}'"
        elif event_type == "final_baler":
            msg = f"■□□■ Track Final Baler: '{track.get('info')}' in '{zone}'"
        elif event_type == "exited":
            msg = f"■■■□ Track Exited: '{track.get('info')}' → '{zone}'"
        elif event_type == "removed":
            msg = f"■■■■ Track Removed: '{track.get('info')}'"
        else:
            self.log_error(f"Unknown event type: {event_type}")
            return None
        self.log_info(msg)
        self.event_messages.add(msg, track.get('color'))
        return evt