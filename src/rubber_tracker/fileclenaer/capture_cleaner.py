"""
CaptureCleaner — 오래된 캡쳐 이미지(.jpg) 를 자동으로 삭제하는 주기 서비스.

CaptureService 는 다음 구조로 이미지를 저장한다:
    bbox_capture.save_dir / <YYYY-MM-DD> / <gate_name> / <ts>.jpg

따라서 스캔 root 는 bbox_capture.save_dir 의 부모 디렉토리로 잡고,
target_dirs 에 captures 폴더명을 두면 날짜 하위 폴더까지 재귀적으로 정리된다.

기본값:
  - root           : dirname(bbox_capture.save_dir) 또는 "results"
  - target_dirs    : [basename(bbox_capture.save_dir)] 또는 ["captures"]
  - file_extensions: [".jpg"]

구성 (config/base.yaml 의 capture_cleaner 섹션):
  capture_cleaner:
    enabled: true
    retention_hours: 720           # 30 일. 0 이면 즉시 삭제
    thread_interval: 3600
    target_dirs:
      - "captures"
    file_extensions:
      - ".jpg"
    dry_run: false
"""

import os

from rubber_tracker.utils import load_config

from .base_cleaner import BaseFileCleaner


class CaptureCleaner(BaseFileCleaner):
    DEFAULT_FILE_EXTENSIONS = [".jpg"]

    def __init__(self):
        cfg = load_config()
        bbox_cfg = cfg.get("bbox_capture", {}) or {}
        cleaner_cfg = cfg.get("capture_cleaner", {}) or {}

        # bbox_capture.save_dir 를 기준으로 root / target_dirs 의 안전한 기본값을 도출.
        # save_dir = "results/captures" 인 경우 → root="results", target=["captures"]
        save_dir = bbox_cfg.get("save_dir") or "results/captures"
        save_dir_abs = os.path.abspath(save_dir)
        root = os.path.dirname(save_dir_abs) or os.sep
        default_target = os.path.basename(save_dir_abs) or "captures"

        super().__init__(
            name=self.__class__.__name__,
            root=root,
            cleaner_cfg=cleaner_cfg,
            default_target_dirs=[default_target],
            default_file_extensions=self.DEFAULT_FILE_EXTENSIONS,
            # 캡쳐 폴더는 날짜/게이트 단위로 동적으로 만들어지므로,
            # 비면 같이 정리되는 게 자연스럽다 (다음 저장 시 makedirs 로 재생성).
            default_remove_empty_dirs=True,
        )
