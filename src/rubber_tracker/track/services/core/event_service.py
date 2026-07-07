import threading
from datetime import datetime

from rubber_tracker.utils import ProcessLogger


class EventService(ProcessLogger):
    def __init__(self, event_messages, event_cfg, camera_id):
        super().__init__(self.__class__.__name__)
        self._validate_event_cfg(event_cfg)

        self.event_messages = event_messages
        self.camera_id = str(camera_id)
        self._event_cfg = event_cfg
        self._event_kinds = tuple(event_cfg.keys())
        
        self._lock = threading.Lock()
        self._counts = {k: 0 for k in self._event_kinds}
        self._notifier_send = None

    def build_event(self, track, zone, event_type, rejected=False):
        meta = self._event_cfg.get(event_type)
        if meta is None:
            self.log_error(f"build_event: unknown event type: {event_type}")
            return None

        symbol = meta["symbol"]
        data_type = meta["data_type"]
        event_desc = f"{event_type}_{zone}"

        evt = {
            'type': data_type,
            'id': track.get('id'),
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            'zone': zone,
            'baler': track.get('valid_baler'),
            'rejected': rejected,
            'event': event_desc,
            'input_baler': track.get('input_baler') if 'input_baler' in track else track.get('baler'),
            'final_baler': track.get('final_baler'),
        }

        display_id = track.get('info') or track.get('id')
        msg = f"{symbol} {event_type}: '{display_id}' in '{zone}'"

        with self._lock:
            self._counts[event_type] += 1
            evt["event_count"] = self._counts[event_type]

        self._notify_track_event_counts()

        self.log_info(msg)
        self.event_messages.add(msg, track.get('color'))
        return evt

    def set_notifier_send(self, fn):
        """페이로드 dict 를 notifier 로 보내는 콜백 (NetworkEventHub.send_track_event_count)."""
        self._notifier_send = fn

    def apply_remote_reset(self, meta):
        """notifier 수신 type=track_event_count_reset 의 meta.counts 에 있는 키만 반영."""
        counts = (meta or {}).get("counts") or {}
        if not isinstance(counts, dict) or not counts:
            return
        with self._lock:
            for k, v in counts.items():
                ks = str(k)
                if ks not in self._event_kinds:
                    self.log_warning(f"track_event_count_reset: unknown event kind: {ks}")
                    continue
                try:
                    self._counts[ks] = int(v)
                except (TypeError, ValueError):
                    self.log_warning(f"track_event_count_reset: skip invalid {ks}={v!r}")
        self.log_info(f"event counts reset (remote): {counts}")

    def _notify_track_event_counts(self):
        if self._notifier_send is None:
            return
        with self._lock:
            counts = {k: self._counts[k] for k in self._event_kinds}
        payload = {
            "type": "track_event_count",
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
            "camera_id": self.camera_id,
            "meta": {"counts": counts},
        }
        self._notifier_send(payload)

    @staticmethod
    def _validate_event_cfg(cfg):
        if not isinstance(cfg, dict):
            raise ValueError("event config must be a mapping")
        for k, meta in cfg.items():
            if not isinstance(meta, dict):
                raise ValueError(f"event['{k}'] must be a mapping with symbol/data_type")
            if "symbol" not in meta or "data_type" not in meta:
                raise ValueError(f"event['{k}'] requires both 'symbol' and 'data_type'")