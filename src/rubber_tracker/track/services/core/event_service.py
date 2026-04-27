import threading
from datetime import datetime

from rubber_tracker.utils import ProcessLogger

# build_event 의 event_type 인자와 동일한 키 (존별 full type 이 아닌 종류별 집계)
_EVENT_KINDS = (
    "id_added",
    "created",
    "weigher_in",
    "weigher_out",
    "final_baler",
    "exited",
    "removed",
)


class EventService(ProcessLogger):
    """
    Builds event payloads and routes messages into EventMessage system.
    이벤트 종류별 누적 카운트를 유지하며, evt 에 event_count 를 넣는다.
    초기값은 load_config 로 병합된 event_counts.initial 만 사용한다.
    카운트가 바뀔 때마다 network.notifier 로 type=track_event_count 페이로드를 보낸다.
    """

    def __init__(self, event_messages, initial_counts=None, camera_id=""):
        super().__init__(self.__class__.__name__)
        self.event_messages = event_messages
        self.camera_id = str(camera_id or "")
        initial_counts = initial_counts or {}
        self._lock = threading.Lock()
        self._counts = {k: int(initial_counts.get(k, 0)) for k in _EVENT_KINDS}
        self._notifier_send = None

    def set_notifier_send(self, fn):
        """페이로드 dict 를 notifier 로 보내는 콜백 (NetworkEventHub.send_track_event_count)."""
        self._notifier_send = fn

    def _notify_track_event_counts(self):
        if self._notifier_send is None:
            return
        with self._lock:
            counts = {k: self._counts[k] for k in _EVENT_KINDS}
        payload = {
            "type": "track_event_count",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "camera_id": self.camera_id,
            "meta": {"counts": counts},
        }
        self._notifier_send(payload)

    def apply_remote_reset(self, meta):
        """notifier 수신 type=track_event_count_reset 의 meta.counts 에 있는 키만 반영."""
        counts = (meta or {}).get("counts") or {}
        if not isinstance(counts, dict) or not counts:
            return
        with self._lock:
            for k, v in counts.items():
                ks = str(k)
                if ks not in _EVENT_KINDS:
                    self.log_warning(f"track_event_count_reset: unknown event kind: {ks}")
                    continue
                try:
                    self._counts[ks] = int(v)
                except (TypeError, ValueError):
                    self.log_warning(f"track_event_count_reset: skip invalid {ks}={v!r}")
        self.log_info(f"event counts reset (remote): {counts}")

    def get_event_counts(self):
        """이벤트 종류별 현재 카운트 스냅샷 (복사본)."""
        with self._lock:
            return dict(self._counts)

    def build_event(self, track, zone, event_type="created", rejected=False):
        evt = {
            'id': track.get('id'),
            'input_baler': track.get('input_baler') if 'input_baler' in track else track.get('baler'),
            'final_baler': track.get('final_baler'),
            'baler': track.get('valid_baler'),
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

        with self._lock:
            self._counts[event_type] = self._counts.get(event_type, 0) + 1
            evt["event_count"] = self._counts[event_type]

        self._notify_track_event_counts()

        self.log_info(msg)
        self.event_messages.add(msg, track.get('color'))
        return evt