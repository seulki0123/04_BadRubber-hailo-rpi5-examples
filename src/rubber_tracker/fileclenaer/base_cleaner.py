"""
BaseFileCleaner — 공통 파일 정리 베이스 클래스.

LogCleaner / CaptureCleaner / RecordingCleaner 가 공유하는 "주기 스캔 →
보존기간 경과 파일 삭제 (+ 옵션으로 빈 폴더 제거)" 로직을 한 곳으로 모은다.
서브클래스는 자기 도메인에 맞는 root / 기본값만 주입하면 된다.

동작 방식:
  1. CustomThread 가 config 로 지정된 주기(초) 마다 task() 호출.
  2. self.root 아래 self.target_dirs 를 스캔.
  3. mtime 이 retention_hours 시간 이상 지난 파일만 대상.
     → 파일명 파싱이 아닌 mtime 기준이므로 TimedRotatingFileHandler 가 만드는
       "*.log.YYYY-MM-DD" 같은 rotated 파일도 안전하게 처리.
  4. 확장자 화이트리스트(file_extensions) 통과한 파일만 삭제.
  5. remove_empty_dirs=true 면, 파일 정리 후 target_dirs 하위에서
     비어있는 폴더(애초에 비어있던 폴더 포함) 를 bottom-up 으로 제거.
  6. dry_run=true 면 삭제하지 않고 "삭제 예정" 로그만 남김 (파일/폴더 모두).

안전 장치:
  - 스캔 범위는 항상 self.root 하위로 제한 → 임의 경로 절대 삭제 불가.
  - root 자체는 어떤 경우에도 삭제하지 않음 (target_dirs 가 root 와 같아도).
  - 확장자 화이트리스트 미통과 시 무시 (예: .py / .json / .yaml 보호).
  - 심볼릭 링크는 따라가지 않음 (os.walk(..., followlinks=False)).
  - 모든 예외는 @safe_call 로 흡수 → 메인 파이프라인에 영향 없음.
  - enabled=false 이면 task 가 no-op.
"""

import os
import time
from typing import List, Tuple

from rubber_tracker.utils import MonitorLogger, safe_call


class BaseFileCleaner(MonitorLogger):
    """주기 호출되는 파일 정리 서비스의 공통 베이스.

    ResourceMonitor / VoltageMonitor 와 동일한 패턴: task() 를 외부에서
    주기적으로 호출받는다. 실행 제어는 FileCleanerService 가 CustomThread 로
    감싸서 담당한다.
    """

    _DEFAULTS = {
        "enabled": True,
        "retention_hours": 720,    # 30 일 (= 24 * 30)
        "thread_interval": 3600,   # 1 시간
        "dry_run": False,
    }

    def __init__(
        self,
        *,
        name: str,
        root: str,
        cleaner_cfg: dict,
        default_target_dirs: List[str],
        default_file_extensions: List[str],
        default_remove_empty_dirs: bool = False,
    ):
        """
        Args:
            name: 인스턴스 이름 (로그 prefix).
            root: 스캔 경계가 되는 디렉터리. 이 밖으로 절대 나가지 않음.
            cleaner_cfg: config dict (enabled / retention_hours / thread_interval /
                target_dirs / file_extensions / dry_run / remove_empty_dirs).
            default_target_dirs: cleaner_cfg.target_dirs 미지정 시 사용.
            default_file_extensions: cleaner_cfg.file_extensions 미지정 시 사용.
            default_remove_empty_dirs: cleaner_cfg.remove_empty_dirs 미지정 시 사용.
                CaptureCleaner / RecordingCleaner 처럼 날짜/세션 단위 폴더가 비면
                같이 정리되는 게 자연스러운 경우 True. LogCleaner 처럼 폴더가
                항상 유지돼야 하는 경우 False.
        """
        super().__init__(name)
        cleaner_cfg = cleaner_cfg or {}

        # 스캔 루트는 항상 절대경로로 정규화 (`..` 이탈 검출이 단순해짐)
        self.root = os.path.abspath(root)

        self.enabled = bool(cleaner_cfg.get("enabled", self._DEFAULTS["enabled"]))
        # retention_hours: 0 도 유효(=즉시 삭제), float 도 허용 (예: 0.1 = 6분).
        # 음수/문자열 등 잘못된 값만 default 로 fallback.
        self.retention_hours = self._to_non_negative_number(
            cleaner_cfg.get("retention_hours"), self._DEFAULTS["retention_hours"]
        )
        self.thread_interval = self._to_positive_int(
            cleaner_cfg.get("thread_interval"), self._DEFAULTS["thread_interval"]
        )
        self.dry_run = bool(cleaner_cfg.get("dry_run", self._DEFAULTS["dry_run"]))
        self.remove_empty_dirs = bool(
            cleaner_cfg.get("remove_empty_dirs", default_remove_empty_dirs)
        )

        target_dirs = cleaner_cfg.get("target_dirs")
        if not isinstance(target_dirs, (list, tuple)) or not target_dirs:
            target_dirs = default_target_dirs
        self.target_dirs: List[str] = [str(d) for d in target_dirs]

        file_exts = cleaner_cfg.get("file_extensions")
        if not isinstance(file_exts, (list, tuple)) or not file_exts:
            file_exts = default_file_extensions
        # 비교 시 대소문자 무시를 위해 소문자로 정규화
        self.file_extensions: List[str] = [str(e).lower() for e in file_exts]

        # 누적 지표 (모니터링용). _total_skipped 는 "스캔된 파일 수" 누계.
        self._total_deleted: int = 0
        self._total_skipped: int = 0
        self._total_dirs_removed: int = 0

        self.log_info(
            f"{name} init | enabled={self.enabled} | retention_hours={self.retention_hours:g} | "
            f"interval={self.thread_interval}s | root={self.root} | "
            f"target_dirs={self.target_dirs} | ext_whitelist={self.file_extensions} | "
            f"dry_run={self.dry_run} | remove_empty_dirs={self.remove_empty_dirs}"
        )

    # ------------------------------------------------------------
    # CustomThread 가 주기적으로 호출하는 엔트리포인트
    # ------------------------------------------------------------
    @safe_call
    def task(self) -> None:
        """주기 실행 엔트리. 모든 예외는 @safe_call 로 흡수된다."""
        if not self.enabled:
            return

        if not os.path.isdir(self.root):
            # 루트가 아직 생성되지 않았을 수 있음 → 다음 주기에 다시 시도
            self.log_warning(f"root does not exist yet: {self.root}")
            return

        deleted, scanned, freed_bytes = self._scan_and_clean()
        self._total_deleted += deleted
        self._total_skipped += scanned

        # 옵션: 파일 정리 후 빈 폴더 (애초에 비어있던 폴더 포함) 도 정리
        dirs_removed = 0
        if self.remove_empty_dirs:
            dirs_removed = self._remove_empty_dirs_in_targets()
            self._total_dirs_removed += dirs_removed

        freed_mb = freed_bytes / (1024 * 1024)
        mode = "DRY-RUN" if self.dry_run else "DELETED"
        if deleted > 0 or dirs_removed > 0:
            self.log_info(
                f"[{mode}] {deleted} file(s) + {dirs_removed} dir(s), freed {freed_mb:.2f}MB | "
                f"cumulative: deleted={self._total_deleted} "
                f"dirs_removed={self._total_dirs_removed} skipped={self._total_skipped}"
            )
        else:
            self.log_debug(f"scan complete: nothing to {mode.lower()} (scanned={scanned})")

    # ------------------------------------------------------------
    # 내부 구현
    # ------------------------------------------------------------
    def _scan_and_clean(self) -> Tuple[int, int, int]:
        """target_dirs 를 순회하며 기간 경과 파일을 삭제.

        Returns:
            (deleted_count, scanned_count, freed_bytes)
        """
        threshold_sec = self.retention_hours * 3600
        now = time.time()

        deleted = 0
        scanned = 0
        freed_bytes = 0

        for sub in self.target_dirs:
            scan_dir = os.path.abspath(os.path.join(self.root, sub))

            # 안전: root 밖으로 빠진 경우 차단 (`..` 같은 설정 방어)
            if not self._is_within_root(scan_dir):
                self.log_warning(f"target_dir '{sub}' escapes root; skipping")
                continue

            if not os.path.isdir(scan_dir):
                # 아직 생성되지 않은 하위 폴더는 조용히 skip
                continue

            # followlinks=False: 심볼릭 링크로 root 밖을 가리키는 공격/사고 방지
            for current_root, _dirs, files in os.walk(scan_dir, followlinks=False):
                if not self._is_within_root(os.path.abspath(current_root)):
                    continue

                for fname in files:
                    scanned += 1
                    fpath = os.path.join(current_root, fname)

                    if not self._is_allowed_extension(fname):
                        continue

                    try:
                        mtime = os.path.getmtime(fpath)
                    except OSError as e:
                        self.log_warning(f"stat failed ({fpath}): {e}")
                        continue

                    age_sec = now - mtime
                    if age_sec < threshold_sec:
                        continue

                    # 삭제 전 메트릭용 크기 조회. 실패해도 삭제는 진행.
                    try:
                        size = os.path.getsize(fpath)
                    except OSError:
                        size = 0

                    if self.dry_run:
                        self.log_info(
                            f"[DRY-RUN] would delete: {fpath} "
                            f"(age={age_sec / 3600:.1f}h, size={size}B)"
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
                        f"deleted: {fpath} (age={age_sec / 3600:.1f}h, size={size}B)"
                    )

        return deleted, scanned, freed_bytes

    def _remove_empty_dirs_in_targets(self) -> int:
        """target_dirs 하위에서 빈 폴더를 bottom-up 으로 제거.

        - 파일이 모두 정리된 후 호출되므로, 안에 아무것도 안 남은 폴더가 대상.
        - 애초에 비어있던 폴더도 대상 (예: 캡쳐가 한 번도 들어오지 않은 게이트 폴더).
        - target_dir 자체도 비어있으면 함께 제거 (CaptureService / Recorder 가
          다음 저장 시 makedirs 로 다시 만들어 주므로 안전).
        - root 자체는 절대 건드리지 않음 (target_dir 가 root 와 동일한 경우 포함).

        Returns: 제거된(또는 dry-run 으로 제거 예정인) 디렉토리 개수.
        """
        removed_total = 0
        for sub in self.target_dirs:
            scan_dir = os.path.abspath(os.path.join(self.root, sub))

            if not self._is_within_root(scan_dir):
                continue
            if not os.path.isdir(scan_dir):
                continue

            removed_total += self._remove_empty_dirs_under(scan_dir)
        return removed_total

    def _remove_empty_dirs_under(self, target_dir: str) -> int:
        """target_dir 하위 + target_dir 자체를 대상으로 빈 폴더 bottom-up 제거.

        os.walk(topdown=False) 가 leaf 부터 순회하므로, 우리가 leaf 를 rmdir 하면
        그 부모는 다음 방문 시 새로 listdir 했을 때 비어있게 보임 → 자연스럽게
        bottom-up cascade 가 동작.
        """
        removed = 0
        for current_root, _dirs, _files in os.walk(target_dir, topdown=False, followlinks=False):
            abs_current = os.path.abspath(current_root)

            # 안전 가드: root 자체는 절대 제거 금지
            if abs_current == self.root:
                continue
            if not self._is_within_root(abs_current):
                continue

            try:
                entries = os.listdir(abs_current)
            except OSError as e:
                self.log_warning(f"listdir failed ({abs_current}): {e}")
                continue

            if entries:
                # 아직 뭐가 남아있음 (다른 확장자 파일 / 보호 대상 등) → 보존
                continue

            if self.dry_run:
                self.log_info(f"[DRY-RUN] would remove empty dir: {abs_current}")
                removed += 1
                continue

            try:
                os.rmdir(abs_current)
            except OSError as e:
                self.log_warning(f"rmdir failed ({abs_current}): {e}")
                continue

            removed += 1
            self.log_info(f"removed empty dir: {abs_current}")

        return removed

    # ------------------------------------------------------------
    # 헬퍼
    # ------------------------------------------------------------
    def _is_within_root(self, path: str) -> bool:
        """path 가 self.root 하위인지 검증 (`..` 이탈 방지)."""
        try:
            abs_path = os.path.abspath(path)
            root_with_sep = self.root + os.sep
            return abs_path == self.root or abs_path.startswith(root_with_sep)
        except Exception:
            return False

    def _is_allowed_extension(self, filename: str) -> bool:
        """확장자 화이트리스트 통과 여부.

        허용 규칙:
          - 정확히 ext 로 끝나는 경우 (예: ".log" → "foo.log")
          - ext. 형태로 포함되는 rotated 파일 (예: ".log" → "foo.log.2026-04-14")
        """
        name_lower = filename.lower()
        for ext in self.file_extensions:
            if name_lower.endswith(ext):
                return True
            rotated_marker = ext + "."
            if rotated_marker in name_lower:
                return True
        return False

    @staticmethod
    def _to_positive_int(value, default: int) -> int:
        """config 값을 양의 정수로 안전 변환. 실패 시 default 반환.

        thread_interval 처럼 0 이면 무한 루프/부하 위험이 있는 값에 사용.
        """
        try:
            n = int(value)
            return n if n > 0 else default
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _to_non_negative_number(value, default):
        """config 값을 0 이상의 숫자(int/float) 로 안전 변환. 음수/형변환 실패 시 default.

        retention_hours 처럼 0 (= 즉시 삭제) 도 유효하고, 시간 미만 단위
        (예: 0.1시간 = 6분) 가 의미 있는 항목에 사용.
        """
        try:
            n = float(value)
            return n if n >= 0 else default
        except (TypeError, ValueError):
            return default
