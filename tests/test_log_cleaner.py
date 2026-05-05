"""
Unit tests for fileclenaer.log_cleaner module.

실행:
    cd 프로젝트루트
    PYTHONPATH=src python -m pytest tests/test_log_cleaner.py -v

외부 의존성(Hailo NPU, GStreamer, IP 카메라) 없이 LogCleaner 의 동작을
독립 검증한다. conftest.py 의 stub 로 macOS/Windows 개발 환경에서도 실행 가능.

테스트 전략:
  - 임시 디렉토리(tmp_path) 를 log_root 로 사용하도록 LogCleaner 인스턴스의 속성을 덮어씀.
  - 각 테스트는 독립 LogCleaner 인스턴스 + 독립 파일을 다룸.
  - 파일 mtime 은 os.utime 으로 강제 설정해 "오래된 파일" 상황을 시뮬레이션.
"""

import os
import sys
import time

import pytest

# -----------------------------------------------------------------
# 모듈 임포트 (conftest.py 에서 sys.path 와 stub 처리)
# -----------------------------------------------------------------
from rubber_tracker.fileclenaer import LogCleaner


# -----------------------------------------------------------------
# 공용 헬퍼
# -----------------------------------------------------------------
def _make_cleaner(tmp_path, **overrides):
    """load_config 기본값으로 초기화 후, tmp_path 를 log_root 로 강제 치환.

    LogCleaner 는 생성자에서 load_config 를 호출하므로 테스트마다 config 를
    갈아끼우는 대신 인스턴스 속성만 override 하는 쪽이 간단하고 안정적.
    """
    cleaner = LogCleaner()
    cleaner.log_root = str(tmp_path)
    # 기본값으로 안전한 테스트용 값 세팅
    cleaner.enabled = True
    cleaner.retention_hours = 720          # = 30 일
    cleaner.thread_interval = 3600
    cleaner.target_dirs = ["process", "monitor"]
    cleaner.file_extensions = [".log"]
    cleaner.dry_run = False

    # 테스트별 override 적용
    for k, v in overrides.items():
        if not hasattr(cleaner, k):
            raise AttributeError(f"Unknown LogCleaner attribute: {k}")
        setattr(cleaner, k, v)

    # 누적 지표 초기화 (새 인스턴스여도 안전을 위해 명시적 리셋)
    cleaner._total_deleted = 0
    cleaner._total_skipped = 0
    return cleaner


def _make_file(path, age_days=0, age_seconds=0, content=b"log-line\n"):
    """주어진 경로에 파일을 만들고, (age_days 일 + age_seconds 초) 전 시점으로 mtime 설정.

    분/초 단위 retention 테스트를 위해 age_seconds 옵션 제공.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(content)
    age_total = age_days * 86400 + age_seconds
    if age_total > 0:
        past = time.time() - age_total
        os.utime(path, (past, past))
    return path


# =================================================================
# 기본 동작
# =================================================================
class TestBasic:
    def test_disabled_skips_task(self, tmp_path):
        """enabled=False 면 스캔조차 하지 않는다."""
        cleaner = _make_cleaner(tmp_path, enabled=False)
        p = _make_file(tmp_path / "process" / "old.log", age_days=60)
        cleaner.task()
        assert os.path.exists(p), "disabled 상태에서는 오래된 파일도 보존되어야 함"

    def test_nonexistent_log_root_is_safe(self, tmp_path):
        """log_root 가 없을 때 예외 없이 조용히 반환."""
        cleaner = _make_cleaner(tmp_path / "does_not_exist")
        cleaner.task()  # 예외 없이 통과해야 함

    def test_fresh_files_preserved(self, tmp_path):
        """mtime 이 retention 안쪽인 파일은 남는다."""
        cleaner = _make_cleaner(tmp_path, retention_hours=720)  # 30 일
        p_fresh = _make_file(tmp_path / "process" / "today.log", age_days=5)
        p_old = _make_file(tmp_path / "process" / "old.log", age_days=40)
        cleaner.task()
        assert os.path.exists(p_fresh), "5일 된 파일은 남아야 함 (retention=30일)"
        assert not os.path.exists(p_old), "40일 된 파일은 삭제되어야 함"

    def test_retention_hours_zero_deletes_all(self, tmp_path):
        """retention_hours=0 이면 방금 만든 파일도 mtime 경과 0초 >= 0초 → 삭제."""
        cleaner = _make_cleaner(tmp_path, retention_hours=0)
        fresh = _make_file(tmp_path / "process" / "fresh.log", age_days=0)
        cleaner.task()
        assert not os.path.exists(fresh), \
            "retention_hours=0 이면 모든 파일이 즉시 삭제 대상"

    def test_retention_hours_fractional(self, tmp_path):
        """retention_hours 가 소수면 분 단위 retention 가능 (0.1h = 6분)."""
        cleaner = _make_cleaner(tmp_path, retention_hours=0.1)  # 6분
        fresh = _make_file(tmp_path / "process" / "fresh.log", age_seconds=300)  # 5분 전
        old   = _make_file(tmp_path / "process" / "old.log",   age_seconds=420)  # 7분 전
        cleaner.task()
        assert os.path.exists(fresh), "5분 된 파일은 retention=6분 안쪽 → 보존"
        assert not os.path.exists(old), "7분 된 파일은 retention=6분 초과 → 삭제"

    def test_old_files_deleted(self, tmp_path):
        """여러 하위폴더의 오래된 파일들이 모두 삭제된다."""
        cleaner = _make_cleaner(tmp_path, retention_hours=168)  # 7 일
        targets = [
            tmp_path / "process" / "a.log",
            tmp_path / "process" / "b.log",
            tmp_path / "monitor" / "c.log",
        ]
        for p in targets:
            _make_file(p, age_days=30)
        cleaner.task()
        for p in targets:
            assert not os.path.exists(p), f"{p} 가 삭제되지 않음"
        assert cleaner._total_deleted == 3


# =================================================================
# 확장자 화이트리스트
# =================================================================
class TestExtensionWhitelist:
    def test_non_log_files_preserved(self, tmp_path):
        """비 로그 확장자(.py, .json 등) 는 오래돼도 남아야 함."""
        cleaner = _make_cleaner(tmp_path, retention_hours=168)  # 7 일
        keep_py = _make_file(tmp_path / "process" / "notes.py", age_days=100)
        keep_json = _make_file(tmp_path / "process" / "state.json", age_days=100)
        delete_log = _make_file(tmp_path / "process" / "old.log", age_days=100)
        cleaner.task()
        assert os.path.exists(keep_py), "비 로그 확장자는 보호되어야 함"
        assert os.path.exists(keep_json), "비 로그 확장자는 보호되어야 함"
        assert not os.path.exists(delete_log)

    def test_rotated_log_files_are_caught(self, tmp_path):
        """TimedRotatingFileHandler 가 만드는 '*.log.YYYY-MM-DD' 파일도 삭제 대상."""
        cleaner = _make_cleaner(tmp_path, retention_hours=168)  # 7 일
        p = _make_file(tmp_path / "process" / "2026-03-01.log.2026-03-01", age_days=40)
        cleaner.task()
        assert not os.path.exists(p), "rotated 로그 파일도 삭제되어야 함"

    def test_custom_whitelist(self, tmp_path):
        """file_extensions 를 커스텀 지정 시 그 확장자만 삭제."""
        cleaner = _make_cleaner(tmp_path, file_extensions=[".txt"])
        p_txt = _make_file(tmp_path / "process" / "old.txt", age_days=100)
        p_log = _make_file(tmp_path / "process" / "old.log", age_days=100)
        cleaner.task()
        assert not os.path.exists(p_txt)
        assert os.path.exists(p_log), ".log 는 화이트리스트 밖이므로 보존"


# =================================================================
# dry_run 모드
# =================================================================
class TestDryRun:
    def test_dry_run_does_not_delete(self, tmp_path):
        """dry_run=True 면 삭제되지 않고 지표만 증가."""
        cleaner = _make_cleaner(tmp_path, dry_run=True, retention_hours=168)  # 7 일
        targets = [_make_file(tmp_path / "process" / f"{i}.log", age_days=30) for i in range(3)]
        cleaner.task()
        for p in targets:
            assert os.path.exists(p), "dry_run 모드에선 파일이 유지되어야 함"
        # 지표는 "삭제 예정" 수로 증가
        assert cleaner._total_deleted == 3


# =================================================================
# 경계/방어 (log_root 이탈)
# =================================================================
class TestBoundary:
    def test_target_dir_escapes_root_is_blocked(self, tmp_path):
        """target_dirs 에 '../outside' 같은 경로가 오면 스캔하지 않는다."""
        outside = tmp_path.parent / "outside_xxx"
        outside.mkdir(exist_ok=True)
        victim = outside / "secret.log"
        _make_file(victim, age_days=100)

        cleaner = _make_cleaner(
            tmp_path, target_dirs=["../" + outside.name], retention_hours=168  # 7 일
        )
        cleaner.task()
        assert os.path.exists(victim), "log_root 밖 파일은 절대 삭제되면 안 됨"

    def test_target_dir_not_exists_is_skip(self, tmp_path):
        """target_dirs 하위 폴더가 아직 생성 전이면 조용히 skip."""
        cleaner = _make_cleaner(tmp_path, target_dirs=["not_made_yet"])
        cleaner.task()  # 예외 없이 통과


# =================================================================
# 회귀/견고성
# =================================================================
class TestRobustness:
    def test_invalid_config_falls_back(self, tmp_path):
        """thread_interval / retention_hours 가 잘못된 값일 때 fallback 동작 검증.

        - thread_interval (양수 정수만 유효): _to_positive_int → 0/음수/문자열은 default
        - retention_hours (0 / 소수 도 유효): _to_non_negative_number → 음수/문자열만 default
        """
        _ = _make_cleaner(tmp_path)
        # _to_positive_int: 0 도 default 로 떨어짐 (thread_interval 보호)
        assert LogCleaner._to_positive_int("abc", 30) == 30
        assert LogCleaner._to_positive_int(-5, 30) == 30
        assert LogCleaner._to_positive_int(0, 30) == 30
        assert LogCleaner._to_positive_int(7, 30) == 7
        assert LogCleaner._to_positive_int(None, 30) == 30
        # _to_non_negative_number: 0 통과, float 통과, 음수/문자열은 default
        assert LogCleaner._to_non_negative_number("abc", 720) == 720
        assert LogCleaner._to_non_negative_number(-1, 720) == 720
        assert LogCleaner._to_non_negative_number(-0.5, 720) == 720
        assert LogCleaner._to_non_negative_number(0, 720) == 0
        assert LogCleaner._to_non_negative_number(0.0, 720) == 0.0
        assert LogCleaner._to_non_negative_number(0.1, 720) == 0.1
        assert LogCleaner._to_non_negative_number(24, 720) == 24
        assert LogCleaner._to_non_negative_number("0.25", 720) == 0.25
        assert LogCleaner._to_non_negative_number(None, 720) == 720

    def test_missing_one_target_dir_ok(self, tmp_path):
        """target_dirs 중 일부만 존재해도 존재하는 것만 처리."""
        cleaner = _make_cleaner(tmp_path, target_dirs=["process", "nope"])
        _make_file(tmp_path / "process" / "old.log", age_days=40)
        cleaner.task()
        assert not os.path.exists(tmp_path / "process" / "old.log")

    def test_task_swallows_all_exceptions(self, tmp_path, monkeypatch):
        """예기치 못한 예외 (예: os.walk 폭주) 가 task 를 중단시키지 않는다."""
        cleaner = _make_cleaner(tmp_path)

        def _boom(*a, **kw):
            raise RuntimeError("simulated")

        monkeypatch.setattr(os, "walk", _boom)
        # @safe_call 로 감싸져 있으므로 예외가 전파되지 않아야 함
        cleaner.task()  # 실패 시 예외가 올라오고 여기서 fail


# =================================================================
# 빈 폴더 제거 (remove_empty_dirs)
#   LogCleaner default 는 False. 명시적으로 True 로 켰을 때 동작 확인.
#   CaptureCleaner / RecordingCleaner 에서 default=True 로 주입되는 옵션과
#   동일한 코드 경로를 검증한다.
# =================================================================
class TestRemoveEmptyDirs:
    def test_default_off_keeps_empty_dirs(self, tmp_path):
        """LogCleaner default 는 remove_empty_dirs=False → 빈 폴더 보존."""
        cleaner = _make_cleaner(tmp_path, retention_hours=168)  # 7 일
        empty = tmp_path / "process" / "stale_session"
        empty.mkdir(parents=True)
        cleaner.task()
        assert empty.is_dir(), "default off 에서 빈 폴더는 그대로 유지"

    def test_remove_already_empty_dirs(self, tmp_path):
        """remove_empty_dirs=True 면 애초에 비어있던 폴더도 제거."""
        cleaner = _make_cleaner(tmp_path, remove_empty_dirs=True)
        empty1 = tmp_path / "process" / "empty_a"
        empty2 = tmp_path / "monitor" / "empty_b" / "deeper"
        empty1.mkdir(parents=True)
        empty2.mkdir(parents=True)
        cleaner.task()
        assert not empty1.exists()
        assert not empty2.exists()
        # 부모도 (target_dir 자체) 비었으므로 제거됨
        assert not (tmp_path / "monitor" / "empty_b").exists()

    def test_remove_dir_after_files_deleted(self, tmp_path):
        """파일이 retention 으로 모두 삭제되면 그 폴더도 같이 정리된다."""
        cleaner = _make_cleaner(tmp_path, retention_hours=168, remove_empty_dirs=True)  # 7 일
        session = tmp_path / "process" / "2026-04-01_session"
        _make_file(session / "a.log", age_days=30)
        _make_file(session / "b.log", age_days=30)
        cleaner.task()
        assert not session.exists(), "파일 삭제 후 빈 세션 폴더도 제거되어야 함"

    def test_target_dir_removed_when_emptied(self, tmp_path):
        """target_dir 자체가 비어버리면 그것도 제거 (root 는 보존)."""
        cleaner = _make_cleaner(tmp_path, retention_hours=168, remove_empty_dirs=True)  # 7 일
        _make_file(tmp_path / "process" / "old.log", age_days=30)
        cleaner.task()
        assert not (tmp_path / "process").exists(), \
            "target_dir 가 비면 함께 제거되어야 함"
        assert tmp_path.is_dir(), "root 는 어떤 경우에도 제거되면 안 됨"

    def test_non_empty_dir_preserved(self, tmp_path):
        """다른 확장자(보호 대상) 파일이 남아 있으면 폴더 유지."""
        cleaner = _make_cleaner(tmp_path, retention_hours=168, remove_empty_dirs=True)  # 7 일
        keep = _make_file(tmp_path / "process" / "notes.py", age_days=100)
        delete = _make_file(tmp_path / "process" / "old.log", age_days=30)
        cleaner.task()
        assert not os.path.exists(delete)
        assert os.path.exists(keep)
        assert (tmp_path / "process").is_dir(), \
            ".py 가 남아있으므로 폴더는 보존되어야 함"

    def test_dry_run_does_not_remove_dirs(self, tmp_path):
        """dry_run=True 면 빈 폴더도 실제로 지우지 않는다."""
        cleaner = _make_cleaner(
            tmp_path, dry_run=True, remove_empty_dirs=True, retention_hours=168  # 7 일
        )
        empty = tmp_path / "process" / "session"
        empty.mkdir(parents=True)
        cleaner.task()
        assert empty.is_dir(), "dry-run 에서 빈 폴더는 유지되어야 함"


# =================================================================
# 통합 시나리오
# =================================================================
class TestIntegration:
    def test_end_to_end_scenario(self, tmp_path):
        """여러 폴더/확장자/나이 파일 혼합 시 정확한 선별."""
        cleaner = _make_cleaner(tmp_path, retention_hours=336)  # 14 일

        # 삭제되어야 하는 파일들
        to_delete = [
            _make_file(tmp_path / "process" / "old_a.log", age_days=30),
            _make_file(tmp_path / "process" / "2025.log.2025-12-01", age_days=60),
            _make_file(tmp_path / "monitor" / "old_b.log", age_days=20),
        ]
        # 남아야 하는 파일들
        to_keep = [
            _make_file(tmp_path / "process" / "recent.log", age_days=3),
            _make_file(tmp_path / "process" / "notes.py", age_days=365),
            _make_file(tmp_path / "monitor" / "config.yaml", age_days=100),
        ]

        cleaner.task()

        for p in to_delete:
            assert not os.path.exists(p), f"{p} 가 삭제되지 않음"
        for p in to_keep:
            assert os.path.exists(p), f"{p} 가 잘못 삭제됨"

        assert cleaner._total_deleted == len(to_delete)
