"""
LogCleaner — 오래된 로그 파일을 자동으로 삭제하는 주기 모니터링 서비스.

동작 방식:
  1. `CustomThread` 에 의해 config 로 지정된 주기(초) 마다 `task()` 호출.
  2. `log_dir.root` 아래 `target_dirs` (기본: process, monitor) 를 스캔.
  3. 각 파일의 mtime(최종 수정 시각) 이 `retention_days` 일 이상 지난 것만 대상.
     → 파일명 파싱이 아닌 mtime 기준이므로 TimedRotatingFileHandler 가 만드는
       "*.log" 와 "*.log.2026-04-14" 같은 rotated 파일 모두 안전하게 처리.
  4. 확장자 화이트리스트(`file_extensions`) 를 통과한 파일만 삭제.
  5. `dry_run=true` 이면 삭제하지 않고 "삭제 예정" 로그만 남김.

안전 장치:
  - 스캔 범위는 항상 `log_dir.root` 하위로 제한 → 임의 경로 절대 삭제 불가.
  - 확장자 화이트리스트 미통과 시 무시 (예: `.py`, `.json` 보호).
  - 심볼릭 링크는 따라가지 않음 (`os.walk(..., followlinks=False)`).
  - 모든 예외는 내부에서 흡수 → 다른 모니터링/메인 파이프라인에 영향 없음.
  - `enabled=false` 이면 task 가 no-op (기본값은 enabled=true).

구성 (config/base.yaml 의 log_cleaner 섹션):
  log_cleaner:
    enabled: true
    retention_days: 30         # 30일보다 오래된 파일 삭제
    thread_interval: 3600      # 1시간마다 점검 (초)
    target_dirs:               # log_dir.root 아래의 하위 폴더만
      - "process"
      - "monitor"
    file_extensions:           # 삭제 허용 확장자 (정확 일치 또는 .log.* 접두 일치)
      - ".log"
    dry_run: false             # true 면 실제 삭제하지 않음 (로그만)
"""

import os
import time
from typing import List, Tuple

from rubber_tracker.utils import MonitorLogger, safe_call, load_config


class LogCleaner(MonitorLogger):
    """오래된 로그 파일을 주기적으로 삭제하는 서비스.

    ResourceMonitor / VoltageMonitor 와 동일하게 `task()` 를 외부에서 주기적으로
    호출받는 방식으로 설계. 실행 제어는 `monitoring.Monitoring.run()` 이
    `CustomThread` 로 감싸서 담당한다.
    """

    # 안전 기본값 — config 누락 시에도 위험 없는 동작 보장
    _DEFAULTS = {
        "enabled": True,
        "retention_days": 30,
        "thread_interval": 3600,          # 1시간
        "target_dirs": ["process", "monitor"],
        "file_extensions": [".log"],
        "dry_run": False,
    }

    def __init__(self):
        super().__init__(self.__class__.__name__)
        cfg = load_config()

        log_dir_cfg = cfg.get("log_dir", {}) or {}
        cleaner_cfg = cfg.get("log_cleaner", {}) or {}

        # 스캔 루트: log_dir.root 가 항상 경계. 이 밖은 절대 접근하지 않음.
        self.log_root = os.path.abspath(log_dir_cfg.get("root", "logs"))

        self.enabled = bool(cleaner_cfg.get("enabled", self._DEFAULTS["enabled"]))
        self.retention_days = self._to_positive_int(
            cleaner_cfg.get("retention_days"), self._DEFAULTS["retention_days"]
        )
        self.thread_interval = self._to_positive_int(
            cleaner_cfg.get("thread_interval"), self._DEFAULTS["thread_interval"]
        )
        self.dry_run = bool(cleaner_cfg.get("dry_run", self._DEFAULTS["dry_run"]))

        # target_dirs / file_extensions 는 정상 list 가 아닐 경우 기본값으로 fallback
        target_dirs = cleaner_cfg.get("target_dirs")
        if not isinstance(target_dirs, (list, tuple)) or not target_dirs:
            target_dirs = self._DEFAULTS["target_dirs"]
        self.target_dirs: List[str] = [str(d) for d in target_dirs]

        file_exts = cleaner_cfg.get("file_extensions")
        if not isinstance(file_exts, (list, tuple)) or not file_exts:
            file_exts = self._DEFAULTS["file_extensions"]
        # 모두 소문자로 정규화해 비교 시 대소문자 무시
        self.file_extensions: List[str] = [str(e).lower() for e in file_exts]

        # 누적 지표 (모니터링용)
        self._total_deleted: int = 0
        self._total_skipped: int = 0

        self.log_info(
            f"LogCleaner init | enabled={self.enabled} | retention_days={self.retention_days} | "
            f"interval={self.thread_interval}s | target_dirs={self.target_dirs} | "
            f"ext_whitelist={self.file_extensions} | dry_run={self.dry_run}"
        )

    # ------------------------------------------------------------
    # CustomThread 가 주기적으로 호출하는 엔트리포인트
    # ------------------------------------------------------------
    @safe_call
    def task(self) -> None:
        """주기 실행 엔트리. 모든 예외는 @safe_call 로 흡수된다."""
        if not self.enabled:
            return

        if not os.path.isdir(self.log_root):
            # 로그 루트가 아직 생성되지 않았을 수 있음 → 다음 주기에 다시 시도
            self.log_warning(f"log_root does not exist yet: {self.log_root}")
            return

        deleted, skipped, freed_bytes = self._scan_and_clean()
        self._total_deleted += deleted
        self._total_skipped += skipped

        # 결과 로깅 (실제 삭제 시 항상 기록, 아무 것도 없을 땐 debug 수준)
        freed_mb = freed_bytes / (1024 * 1024)
        mode = "DRY-RUN" if self.dry_run else "DELETED"
        if deleted > 0:
            self.log_info(
                f"[{mode}] {deleted} file(s), freed {freed_mb:.2f}MB | "
                f"cumulative: deleted={self._total_deleted} skipped={self._total_skipped}"
            )
        else:
            self.log_debug(f"scan complete: nothing to {mode.lower()} (scanned={skipped})")

    # ------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------
    def _scan_and_clean(self) -> Tuple[int, int, int]:
        """target_dirs 를 순회하며 기간 경과 파일을 삭제.

        Returns:
            (deleted_count, scanned_count, freed_bytes)
        """
        threshold_sec = self.retention_days * 24 * 3600
        now = time.time()

        deleted = 0
        scanned = 0
        freed_bytes = 0

        for sub in self.target_dirs:
            # 각 target_dir 를 log_root 와 결합해 절대경로로 정규화
            scan_dir = os.path.abspath(os.path.join(self.log_root, sub))

            # 안전: log_root 밖으로 빠진 경우 차단 (`..` 같은 설정 방어)
            if not self._is_within_root(scan_dir):
                self.log_warning(f"target_dir '{sub}' escapes log_root; skipping")
                continue

            if not os.path.isdir(scan_dir):
                # 아직 생성되지 않은 하위 폴더는 조용히 skip
                continue

            # followlinks=False: 심볼릭 링크로 레포 밖을 가리키는 공격/사고 방지
            for root, _dirs, files in os.walk(scan_dir, followlinks=False):
                # root 역시 log_root 경계 안에 있는지 재확인
                if not self._is_within_root(os.path.abspath(root)):
                    continue

                for fname in files:
                    scanned += 1
                    fpath = os.path.join(root, fname)

                    # 1) 확장자 화이트리스트 검사
                    if not self._is_allowed_extension(fname):
                        continue

                    # 2) mtime 기반 경과 판정
                    try:
                        mtime = os.path.getmtime(fpath)
                    except OSError as e:
                        self.log_warning(f"stat failed ({fpath}): {e}")
                        continue

                    age_sec = now - mtime
                    if age_sec < threshold_sec:
                        continue

                    # 3) 크기 조회 (삭제 전 메트릭용). 실패해도 삭제는 진행.
                    try:
                        size = os.path.getsize(fpath)
                    except OSError:
                        size = 0

                    # 4) 실제 삭제 (또는 dry-run)
                    if self.dry_run:
                        self.log_info(
                            f"[DRY-RUN] would delete: {fpath} "
                            f"(age={age_sec / 86400:.1f}d, size={size}B)"
                        )
                        deleted += 1
                        freed_bytes += size
                        continue

                    try:
                        os.remove(fpath)
                    except OSError as e:
                        self.log_warning(f"remove failed ({fpath}): {e}")
                        continue

                    deleted += 1
                    freed_bytes += size
                    self.log_info(
                        f"deleted: {fpath} (age={age_sec / 86400:.1f}d, size={size}B)"
                    )

        return deleted, scanned, freed_bytes

    # ------------------------------------------------------------
    # 헬퍼
    # ------------------------------------------------------------
    def _is_within_root(self, path: str) -> bool:
        """path 가 log_root 하위인지 검증 (`..` 이탈 방지)."""
        try:
            abs_path = os.path.abspath(path)
            root = self.log_root + os.sep
            return abs_path == self.log_root or abs_path.startswith(root)
        except Exception:
            return False

    def _is_allowed_extension(self, filename: str) -> bool:
        """확장자 화이트리스트 통과 여부.

        허용 규칙:
          - 정확히 `ext` 로 끝나는 경우 (예: ".log" → "foo.log")
          - `ext.` 형태로 시작하는 rotated 파일 (예: ".log" → "foo.log.2026-04-14")
        """
        name_lower = filename.lower()
        for ext in self.file_extensions:
            if name_lower.endswith(ext):
                return True
            # TimedRotatingFileHandler rotation: foo.log.2026-04-14
            rotated_marker = ext + "."
            if rotated_marker in name_lower:
                # 정확히는 basename 에 "{ext}." 가 포함되는지 확인.
                # 예: "foo.log.2026-04-14" → ".log." 포함 → True
                return True
        return False

    @staticmethod
    def _to_positive_int(value, default: int) -> int:
        """config 값을 양의 정수로 안전 변환. 실패 시 default 반환."""
        try:
            n = int(value)
            return n if n > 0 else default
        except (TypeError, ValueError):
            return default
