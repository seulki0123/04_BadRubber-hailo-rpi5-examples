"""
Unit tests for branch / join log split.

실행:
    PYTHONPATH=src python -m pytest tests/test_log_split.py -v

검증 대상:
  1) LogTypeFilter 확장 — 문자열/리스트 모두 허용
  2) EventService._zone_to_log_type — zone 문자열 → log_type 매핑
  3) EventService.build_event — 이벤트 emit 시 zone 기반 log_type 로 log_info 호출
"""

import io
import logging
from unittest.mock import MagicMock, patch

import pytest

from rubber_tracker.utils.logger import LogTypeFilter, Logger, logger as root_logger
from rubber_tracker.track.services.core.event_service import EventService


# =================================================================
# LogTypeFilter
# =================================================================
class TestLogTypeFilter:
    def _make_record(self, log_type=None):
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="", lineno=0,
            msg="m", args=None, exc_info=None,
        )
        if log_type is not None:
            record.log_type = log_type
        return record

    def test_single_string_matches(self):
        f = LogTypeFilter("process")
        assert f.filter(self._make_record("process")) is True
        assert f.filter(self._make_record("branch")) is False

    def test_single_string_default_to_process(self):
        """log_type 속성이 없는 레코드는 process 로 간주된다."""
        f = LogTypeFilter("process")
        assert f.filter(self._make_record(None)) is True
        f2 = LogTypeFilter("branch")
        assert f2.filter(self._make_record(None)) is False

    def test_list_allows_multiple(self):
        """process.log 핸들러 용도 — process/branch/join 모두 수용."""
        f = LogTypeFilter(["process", "branch", "join"])
        assert f.filter(self._make_record("process")) is True
        assert f.filter(self._make_record("branch")) is True
        assert f.filter(self._make_record("join")) is True
        assert f.filter(self._make_record("monitor")) is False

    def test_set_allows_multiple(self):
        f = LogTypeFilter({"branch", "join"})
        assert f.filter(self._make_record("branch")) is True
        assert f.filter(self._make_record("join")) is True
        assert f.filter(self._make_record("process")) is False


# =================================================================
# EventService._zone_to_log_type
# =================================================================
class TestZoneToLogType:
    @pytest.fixture
    def service(self):
        return EventService(event_messages=MagicMock())

    def test_branch_prefix(self, service):
        assert service._zone_to_log_type("branch_in") == "branch"
        assert service._zone_to_log_type("branch_out_a") == "branch"
        assert service._zone_to_log_type("branch_out_b") == "branch"

    def test_join_prefix(self, service):
        assert service._zone_to_log_type("join_in_a") == "join"
        assert service._zone_to_log_type("join_in_b") == "join"
        assert service._zone_to_log_type("join_out") == "join"

    def test_other_zones_fall_back_to_process(self, service):
        assert service._zone_to_log_type("house_in_a") == "process"
        assert service._zone_to_log_type("weigher_a") == "process"
        assert service._zone_to_log_type("inspector_out_a") == "process"

    def test_none_and_empty(self, service):
        assert service._zone_to_log_type(None) == "process"
        assert service._zone_to_log_type("") == "process"

    def test_non_string(self, service):
        """zone 이 dict/int 등으로 들어와도 안전하게 process 로 떨어져야 한다."""
        assert service._zone_to_log_type(123) == "process"
        assert service._zone_to_log_type({"a": 1}) == "process"


# =================================================================
# EventService.build_event — 이벤트 emit 시 올바른 log_type 전달
# =================================================================
class TestEventBuildRouting:
    def _make_track(self, track_id="ext-1"):
        # TrackState.to_dict() 결과를 흉내 낸 최소 dict.
        return {
            "id": track_id,
            "info": "track_info",
            "input_baler": 10,
            "final_baler": None,
            "valid_baler": 11,
            "color": (0, 0, 0),
        }

    @pytest.fixture
    def service(self):
        return EventService(event_messages=MagicMock())

    def _capture_log_type(self, service, monkeypatch):
        """service.log_info 를 가로채 kwargs 의 log_type 를 캡처."""
        captured = {}

        def fake_log_info(message, color=None, log_type="process"):
            captured["msg"] = message
            captured["log_type"] = log_type

        monkeypatch.setattr(service, "log_info", fake_log_info)
        return captured

    @pytest.mark.parametrize("zone,event_type,expected", [
        ("branch_in", "created", "branch"),
        ("branch_out_a", "exited", "branch"),
        ("join_in_a", "created", "join"),
        ("join_in_b", "weigher_in", "join"),  # prefix 는 join_ 이므로 join
        ("join_out", "exited", "join"),
        ("house_in_a", "weigher_in", "process"),
        ("weigher_a", "weigher_out", "process"),
        (None, "removed", "process"),
    ])
    def test_log_type_dispatch(self, service, monkeypatch, zone, event_type, expected):
        captured = self._capture_log_type(service, monkeypatch)
        evt = service.build_event(self._make_track(), zone, event_type=event_type)
        assert evt is not None, "이벤트 빌드 실패 — 시나리오 설정 오류"
        assert captured["log_type"] == expected, (
            f"zone={zone!r}, event={event_type!r} → "
            f"기대 {expected!r}, 실제 {captured['log_type']!r}"
        )

    def test_event_messages_still_recorded(self, service, monkeypatch):
        """log_type 이 branch 여도 EventMessage 기록은 그대로 동작."""
        self._capture_log_type(service, monkeypatch)
        evt = service.build_event(self._make_track(), "branch_in", event_type="created")
        assert evt is not None
        service.event_messages.add.assert_called_once()

    def test_unknown_event_type_returns_none(self, service, monkeypatch):
        """알 수 없는 event_type 은 None 반환 + 에러 로그."""
        captured = self._capture_log_type(service, monkeypatch)
        # log_error 는 따로 사용되므로 기본 동작 확인 위해 monkeypatch 하지 않음
        evt = service.build_event(self._make_track(), "branch_in", event_type="bogus")
        assert evt is None
        # log_info 는 호출되지 않아야 함
        assert "msg" not in captured


# =================================================================
# 엣지 케이스 — fallback 동작 검증
# =================================================================
class TestLoggerFallbacks:
    """알 수 없는 log_type, 잘못된 config 값 등이 들어와도
    메시지가 유실되지 않고 안전하게 process 로 떨어지는지 검증."""

    def test_unknown_log_type_falls_back_to_process(self, monkeypatch):
        """오타/임의 문자열 → process 로 복구되고 stderr 경고."""
        fake_stderr = io.StringIO()
        monkeypatch.setattr("sys.stderr", fake_stderr)

        assert root_logger._normalize_log_type("bogus") == "process"
        assert "Unknown log_type" in fake_stderr.getvalue()

    def test_known_log_types_pass_through(self):
        """유효한 log_type 은 경고 없이 그대로 반환."""
        for t in ("process", "monitor", "branch", "join"):
            assert root_logger._normalize_log_type(t) == t

    def test_none_log_type_falls_back(self, monkeypatch):
        """None 같은 비문자열도 안전하게 process 로 복구."""
        fake_stderr = io.StringIO()
        monkeypatch.setattr("sys.stderr", fake_stderr)
        assert root_logger._normalize_log_type(None) == "process"

    def test_prepare_split_log_file_returns_none_for_null_folder(self, tmp_path):
        """folder 가 null/빈 문자열이면 경고 없이 None (분기 비활성) 반환."""
        result = root_logger._prepare_split_log_file(
            str(tmp_path), None, "2026-01-01_00-00-00", "branch"
        )
        assert result is None

        result2 = root_logger._prepare_split_log_file(
            str(tmp_path), "", "2026-01-01_00-00-00", "branch"
        )
        assert result2 is None

    def test_prepare_split_log_file_rejects_non_string(self, tmp_path, monkeypatch):
        """folder 가 문자열이 아니면 경고 출력 + None 반환."""
        fake_stderr = io.StringIO()
        monkeypatch.setattr("sys.stderr", fake_stderr)
        result = root_logger._prepare_split_log_file(
            str(tmp_path), 123, "2026-01-01_00-00-00", "branch"
        )
        assert result is None
        assert "must be a string" in fake_stderr.getvalue()

    def test_prepare_split_log_file_creates_dir(self, tmp_path):
        """정상 경로면 디렉토리 생성 + 파일 경로 반환."""
        result = root_logger._prepare_split_log_file(
            str(tmp_path), "branch", "2026-01-01_00-00-00", "branch"
        )
        assert result is not None
        assert (tmp_path / "branch").is_dir()
        assert result.endswith("2026-01-01_00-00-00.log")

    def test_prepare_split_log_file_handles_oserror(self, tmp_path, monkeypatch):
        """디렉토리 생성 실패 (예: 권한 부족) 시 경고 + None 반환.
        os.makedirs 를 OSError 발생으로 치환해 재현."""
        fake_stderr = io.StringIO()
        monkeypatch.setattr("sys.stderr", fake_stderr)

        def raise_oserror(*args, **kwargs):
            raise OSError("permission denied (simulated)")

        monkeypatch.setattr("os.makedirs", raise_oserror)
        result = root_logger._prepare_split_log_file(
            str(tmp_path), "branch", "2026-01-01_00-00-00", "branch"
        )
        assert result is None
        msg = fake_stderr.getvalue()
        assert "Failed to create split log dir" in msg
        # fallback 안내 포함 확인
        assert "combined process log" in msg


# =================================================================
# LogTypeFilter 엣지 — 빈 집합 / 공백 문자열
# =================================================================
class TestLogTypeFilterEdge:
    def test_empty_set_rejects_all(self):
        """빈 집합이면 아무 것도 통과하지 않는다."""
        f = LogTypeFilter([])
        record = logging.LogRecord(
            name="x", level=logging.INFO, pathname="", lineno=0,
            msg="m", args=None, exc_info=None,
        )
        record.log_type = "process"
        assert f.filter(record) is False

    def test_duplicate_in_list_deduped(self):
        """리스트에 중복이 있어도 set 으로 저장되어 정상 동작."""
        f = LogTypeFilter(["process", "process", "branch"])
        # 내부 상태 확인
        assert f.log_types == {"process", "branch"}
