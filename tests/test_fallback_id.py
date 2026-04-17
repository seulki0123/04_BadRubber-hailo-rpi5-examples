"""
Unit tests for FallbackService fallback ID 생성.

검증 대상:
  1) 새 포맷 구조: {device:02d}{error:1d}{counter:03d}_{HHMMSS}
  2) 초 단위 카운터 리셋
  3) 같은 초 내 복수 호출 시 카운터 증가
  4) 재시작 시뮬레이션 (새 인스턴스) → 시간 다르면 ID 중복 없음
  5) 카운터 999 초과 방어
  6) 다른 error_type 간 카운터 독립
  7) 알 수 없는 error_type 처리

실행:
    PYTHONPATH=src python -m pytest tests/test_fallback_id.py -v
"""

import re
import time
from datetime import datetime
from unittest.mock import patch, MagicMock

import pytest

from rubber_tracker.track.services.external.fallback_service import FallbackService


def _make_service(device_id=10):
    return FallbackService(
        device_id=device_id,
        create_fallback_baler_no_externals=10,
        create_fallback_baler_not_input_zone=13,
    )


# 포맷 정규식: DD E CCC _ HHMMSS (총 13자)
ID_PATTERN = re.compile(r"^\d{2}\d{1}\d{3}_\d{6}$")


# =================================================================
# 기본 포맷
# =================================================================
class TestFormat:
    def test_format_matches_pattern(self):
        """생성된 ID 가 DDECC_HHMMSS 13자리 포맷을 따르는지."""
        svc = _make_service(device_id=10)
        _, fb_id = svc.get_fallback_id(2)
        assert ID_PATTERN.match(fb_id), f"포맷 불일치: {fb_id}"
        assert len(fb_id) == 13

    def test_device_and_error_encoded(self):
        """device_id 와 error_type 이 왼쪽에 올바르게 인코딩되는지."""
        svc = _make_service(device_id=10)
        _, fb_id = svc.get_fallback_id(2)
        # 왼쪽 6자: "10" + "2" + "000" (첫 호출이므로 카운터=0)
        left = fb_id.split("_")[0]
        assert left[:2] == "10", f"device 자리 불일치: {left[:2]}"
        assert left[2] == "2", f"error_type 자리 불일치: {left[2]}"

    def test_time_portion_is_valid_hhmmss(self):
        """오른쪽 6자리가 유효한 HHMMSS 범위인지."""
        svc = _make_service()
        _, fb_id = svc.get_fallback_id(2)
        hhmmss = fb_id.split("_")[1]
        hh, mm, ss = int(hhmmss[:2]), int(hhmmss[2:4]), int(hhmmss[4:6])
        assert 0 <= hh <= 23
        assert 0 <= mm <= 59
        assert 0 <= ss <= 59

    def test_different_device_ids(self):
        """device_id 가 다르면 왼쪽 2자리가 달라지는지."""
        svc_a = _make_service(device_id=11)
        svc_b = _make_service(device_id=12)
        _, id_a = svc_a.get_fallback_id(2)
        _, id_b = svc_b.get_fallback_id(2)
        assert id_a[:2] == "11"
        assert id_b[:2] == "12"

    def test_baler_return_value(self):
        """반환 tuple 의 첫 번째 값이 config 의 baler 값과 일치하는지."""
        svc = _make_service()
        baler, _ = svc.get_fallback_id(1)
        assert baler == 13  # create_fallback_baler_not_input_zone
        baler, _ = svc.get_fallback_id(2)
        assert baler == 10  # create_fallback_baler_no_externals


# =================================================================
# 카운터 동작
# =================================================================
class TestCounter:
    def test_counter_increments_within_same_second(self):
        """같은 초 내 연속 호출 시 카운터가 0, 1, 2, ... 증가."""
        svc = _make_service()
        fixed_time = datetime(2026, 4, 16, 15, 30, 45)
        with patch("rubber_tracker.track.services.external.fallback_service.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

            ids = [svc.get_fallback_id(2)[1] for _ in range(5)]

        counters = [int(fb.split("_")[0][3:6]) for fb in ids]
        assert counters == [0, 1, 2, 3, 4]

    def test_counter_resets_on_new_second(self):
        """초가 바뀌면 카운터가 0 으로 리셋."""
        svc = _make_service()
        t1 = datetime(2026, 4, 16, 15, 30, 45)
        t2 = datetime(2026, 4, 16, 15, 30, 46)

        with patch("rubber_tracker.track.services.external.fallback_service.datetime") as mock_dt:
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            # 첫 번째 초에 3개
            mock_dt.now.return_value = t1
            for _ in range(3):
                svc.get_fallback_id(2)
            # 두 번째 초
            mock_dt.now.return_value = t2
            _, fb_id = svc.get_fallback_id(2)

        counter = int(fb_id.split("_")[0][3:6])
        assert counter == 0, f"초 변경 후 카운터 리셋 실패: {counter}"

    def test_counter_independent_per_error_type(self):
        """error_type 별로 카운터가 독립."""
        svc = _make_service()
        fixed_time = datetime(2026, 4, 16, 15, 30, 45)
        with patch("rubber_tracker.track.services.external.fallback_service.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

            _, id_e1 = svc.get_fallback_id(1)
            _, id_e2 = svc.get_fallback_id(2)
            _, id_e1b = svc.get_fallback_id(1)

        # error_type=1: 0, 1 / error_type=2: 0
        assert int(id_e1.split("_")[0][3:6]) == 0
        assert int(id_e2.split("_")[0][3:6]) == 0
        assert int(id_e1b.split("_")[0][3:6]) == 1


# =================================================================
# 유일성 (중복 방지 — 핵심 검증)
# =================================================================
class TestUniqueness:
    def test_no_duplicate_in_rapid_burst(self):
        """같은 초 내 100개 연속 생성 시 전부 고유."""
        svc = _make_service()
        fixed_time = datetime(2026, 4, 16, 15, 30, 45)
        with patch("rubber_tracker.track.services.external.fallback_service.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            ids = [svc.get_fallback_id(2)[1] for _ in range(100)]
        assert len(set(ids)) == 100, "같은 초 내 100개 중 중복 발생"

    def test_no_duplicate_across_restarts(self):
        """재시작 시뮬레이션: 새 인스턴스 + 다른 시간 → 중복 없음."""
        t1 = datetime(2026, 4, 16, 15, 30, 45)
        t2 = datetime(2026, 4, 16, 15, 30, 46)

        ids_run1 = []
        ids_run2 = []

        with patch("rubber_tracker.track.services.external.fallback_service.datetime") as mock_dt:
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

            mock_dt.now.return_value = t1
            svc1 = _make_service()
            for _ in range(10):
                ids_run1.append(svc1.get_fallback_id(2)[1])

            mock_dt.now.return_value = t2
            svc2 = _make_service()  # 재시작 = 새 인스턴스
            for _ in range(10):
                ids_run2.append(svc2.get_fallback_id(2)[1])

        all_ids = ids_run1 + ids_run2
        assert len(set(all_ids)) == 20, "재시작 후 ID 중복 발생"

    def test_same_second_different_error_types_unique(self):
        """같은 초, 다른 error_type → ID 다름 (error_type 자리가 다르므로)."""
        svc = _make_service()
        fixed_time = datetime(2026, 4, 16, 15, 30, 45)
        with patch("rubber_tracker.track.services.external.fallback_service.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            _, id1 = svc.get_fallback_id(1)
            _, id2 = svc.get_fallback_id(2)
        assert id1 != id2


# =================================================================
# 엣지 케이스
# =================================================================
class TestEdgeCases:
    def test_counter_overflow_capped_at_999(self):
        """만에 하나 1초 내 1000개 이상 → 999 에서 멈춤 (포맷 깨지지 않음)."""
        svc = _make_service()
        fixed_time = datetime(2026, 4, 16, 15, 30, 45)
        with patch("rubber_tracker.track.services.external.fallback_service.datetime") as mock_dt:
            mock_dt.now.return_value = fixed_time
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)
            last_id = None
            for _ in range(1005):
                _, last_id = svc.get_fallback_id(2)
        # 포맷이 깨지지 않았는지 (13자, 숫자만)
        assert ID_PATTERN.match(last_id), f"오버플로우 후 포맷 깨짐: {last_id}"
        assert len(last_id) == 13

    def test_unknown_error_type_gets_baler_99(self):
        """등록 안 된 error_type → baler=99 할당, ID 는 정상 생성."""
        svc = _make_service()
        baler, fb_id = svc.get_fallback_id(7)
        assert baler == 99
        assert ID_PATTERN.match(fb_id)

    def test_midnight_rollover(self):
        """23:59:59 → 00:00:00 전환 시 정상 동작."""
        svc = _make_service()
        t1 = datetime(2026, 4, 16, 23, 59, 59)
        t2 = datetime(2026, 4, 17, 0, 0, 0)

        with patch("rubber_tracker.track.services.external.fallback_service.datetime") as mock_dt:
            mock_dt.side_effect = lambda *a, **k: datetime(*a, **k)

            mock_dt.now.return_value = t1
            _, id1 = svc.get_fallback_id(2)
            mock_dt.now.return_value = t2
            _, id2 = svc.get_fallback_id(2)

        assert id1.endswith("235959")
        assert id2.endswith("000000")
        assert id1 != id2
