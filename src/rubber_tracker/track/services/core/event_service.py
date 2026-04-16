from datetime import datetime

from rubber_tracker.utils import ProcessLogger

class EventService(ProcessLogger):
    """
    Builds event payloads and routes messages into EventMessage system.

    zone 이름이 'branch_' 또는 'join_' 으로 시작하는 이벤트는 통합 process.log 에
    기록됨과 동시에 별도의 branch.log / join.log 로도 분기 기록된다.
    (log_dir.branch / log_dir.join 설정이 있을 때만 별도 파일 생성. 기본 활성)
    """

    # zone prefix → 로그 분기 타입
    # 여기에 없는 zone (house_in_*, weigher_*, inspector_out_* 등) 은 통합 로그에만 기록.
    _ZONE_PREFIX_TO_LOG_TYPE = (
        ("branch_", "branch"),
        ("join_", "join"),
    )

    def __init__(self, event_messages):
        super().__init__(self.__class__.__name__)
        self.event_messages = event_messages

    def _zone_to_log_type(self, zone) -> str:
        """zone 이름 앞부분으로 branch / join 분기 대상인지 판정.
        일치하지 않으면 기본 'process' (통합 로그에만 기록)."""
        if not zone or not isinstance(zone, str):
            return "process"
        for prefix, log_type in self._ZONE_PREFIX_TO_LOG_TYPE:
            if zone.startswith(prefix):
                return log_type
        return "process"

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
        # zone 에 따라 log_type 을 결정. process.log 는 통합 로그라 항상 받음.
        log_type = self._zone_to_log_type(zone)
        self.log_info(msg, log_type=log_type)
        self.event_messages.add(msg, track.get('color'))
        return evt