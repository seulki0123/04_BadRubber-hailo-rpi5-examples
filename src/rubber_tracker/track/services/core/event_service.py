import os
import threading
from datetime import datetime

import yaml

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

_SETTING_YAML = "config/setting.yaml"


class EventService(ProcessLogger):
    """
    Builds event payloads and routes messages into EventMessage system.
    이벤트 종류별 누적 카운트를 유지하며, evt 에 event_count 를 넣는다.
    config/setting.yaml 의 event_counts.initial 을 저장하면(mtime 변경) 해당 키만 반영한다.
    """

    def __init__(self, event_messages, initial_counts=None):
        super().__init__(self.__class__.__name__)
        self.event_messages = event_messages
        initial_counts = initial_counts or {}
        self._lock = threading.Lock()
        self._counts = {k: int(initial_counts.get(k, 0)) for k in _EVENT_KINDS}
        # None: 아직 baseline mtime 미설정. 첫 build_event 에서 mtime 만 잡고
        # 파일을 읽지 않는다(load_config 로 이미 반영된 초기값 유지).
        self._setting_yaml_mtime = None

    def get_event_counts(self):
        """이벤트 종류별 현재 카운트 스냅샷 (복사본)."""
        with self._lock:
            return dict(self._counts)

    def _maybe_reload_counts_from_setting_yaml(self):
        """setting.yaml 이 저장되어 바뀌면 event_counts.initial 에 있는 항목만 카운터에 적용."""
        try:
            mtime = os.path.getmtime(_SETTING_YAML)
        except OSError:
            return
        if self._setting_yaml_mtime is None:
            self._setting_yaml_mtime = mtime
            return
        if mtime == self._setting_yaml_mtime:
            return
        self._setting_yaml_mtime = mtime
        try:
            with open(_SETTING_YAML, "r", encoding="utf-8") as f:
                root = yaml.safe_load(f) or {}
        except Exception as e:
            self.log_warning(f"event_counts: failed to read {_SETTING_YAML}: {e}")
            return
        ec = root.get("event_counts") or {}
        if not ec:
            return
        initial = ec.get("initial")
        if not isinstance(initial, dict) or not initial:
            return
        with self._lock:
            for k, v in initial.items():
                ks = str(k)
                if ks not in _EVENT_KINDS:
                    self.log_warning(f"event_counts: unknown event kind in initial: {ks}")
                    continue
                try:
                    self._counts[ks] = int(v)
                except (TypeError, ValueError):
                    self.log_warning(f"event_counts: skip invalid initial for {ks}={v!r}")

    def build_event(self, track, zone, event_type="created", rejected=False):
        self._maybe_reload_counts_from_setting_yaml()

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

        self.log_info(msg)
        self.event_messages.add(msg, track.get('color'))
        return evt