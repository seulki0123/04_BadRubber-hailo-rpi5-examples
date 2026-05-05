"""
LogCleaner — 오래된 로그 파일을 자동으로 삭제하는 주기 서비스.

스캔 root: config.log_dir.root (기본 "logs")
기본 target_dirs: ["process", "monitor"]   (Logger 가 만드는 두 하위 폴더)
기본 file_extensions: [".log"]             (TimedRotatingFileHandler 의 *.log.YYYY-MM-DD 포함)

구성 (config/base.yaml 의 log_cleaner 섹션):
  log_cleaner:
    enabled: true
    retention_hours: 720           # 30 일 (= 24 * 30). 0 이면 즉시 삭제
    thread_interval: 3600          # 1 시간마다 점검 (초)
    target_dirs:
      - "process"
      - "monitor"
    file_extensions:
      - ".log"
    dry_run: false                 # true 면 실제 삭제하지 않고 로그만
"""

import os

from rubber_tracker.utils import load_config

from .base_cleaner import BaseFileCleaner


class LogCleaner(BaseFileCleaner):
    DEFAULT_TARGET_DIRS = ["process", "monitor"]
    DEFAULT_FILE_EXTENSIONS = [".log"]

    def __init__(self):
        cfg = load_config()
        log_dir_cfg = cfg.get("log_dir", {}) or {}
        cleaner_cfg = cfg.get("log_cleaner", {}) or {}

        # log_dir.root 가 항상 스캔 경계. 이 밖은 절대 접근하지 않음.
        root = os.path.abspath(log_dir_cfg.get("root", "logs"))

        super().__init__(
            name=self.__class__.__name__,
            root=root,
            cleaner_cfg=cleaner_cfg,
            default_target_dirs=self.DEFAULT_TARGET_DIRS,
            default_file_extensions=self.DEFAULT_FILE_EXTENSIONS,
        )

    # ------------------------------------------------------------
    # Backward compatibility
    # ------------------------------------------------------------
    # 기존 코드 / 테스트에서 cleaner.log_root 를 참조하는 경우가 있어
    # self.root 에 위임하는 별칭 프로퍼티를 둔다.
    @property
    def log_root(self) -> str:
        return self.root

    @log_root.setter
    def log_root(self, value: str) -> None:
        # 테스트에서 tmp_path 로 강제 치환할 때 사용
        self.root = os.path.abspath(value)
