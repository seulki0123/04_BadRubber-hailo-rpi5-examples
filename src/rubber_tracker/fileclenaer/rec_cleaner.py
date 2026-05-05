"""
RecordingCleaner — Recorder 가 저장하는 오래된 녹화 파일을 자동으로 삭제.

Recorder 는 다음 구조로 결과물을 남긴다 (recorder.py 참조):
    recorder.save_root / <YYYY-MM-DD_HH-MM-SS>_<video_name>/
        <video_name>.mp4              # 비디오
        frames/frame_000001.jpg       # save_frames=True 일 때 프레임 이미지
        frames/frame_000001.txt       # save_frames=True 일 때 bbox 메타

따라서 스캔 root 는 recorder.save_root 의 부모(예: "results"), target_dirs 는
recorder.save_root 의 basename(예: "recordings") 으로 잡으면 날짜 하위 폴더
및 frames/ 까지 재귀적으로 정리된다.

기본값:
  - root           : dirname(recorder.save_root)            (보통 "results")
  - target_dirs    : [basename(recorder.save_root)]         (보통 ["recordings"])
  - file_extensions: [".mp4", ".jpg", ".txt"]               (Recorder 산출물)

구성 (config/base.yaml 의 recording_cleaner 섹션):
  recording_cleaner:
    enabled: true
    retention_hours: 720           # 30 일. 0 이면 즉시 삭제
    thread_interval: 3600
    target_dirs:
      - "recordings"
    file_extensions:
      - ".mp4"
      - ".jpg"
      - ".txt"
    dry_run: false
"""

import os

from rubber_tracker.utils import load_config

from .base_cleaner import BaseFileCleaner


class RecordingCleaner(BaseFileCleaner):
    DEFAULT_FILE_EXTENSIONS = [".mp4", ".jpg", ".txt"]

    def __init__(self):
        cfg = load_config()
        recorder_cfg = cfg.get("recorder", {}) or {}
        cleaner_cfg = cfg.get("recording_cleaner", {}) or {}

        # recorder.save_root 가 "results/recordings" 이면
        # → root="results", target_dirs=["recordings"]
        save_root = recorder_cfg.get("save_root") or "results/recordings"
        save_root_abs = os.path.abspath(save_root)
        root = os.path.dirname(save_root_abs) or os.sep
        default_target = os.path.basename(save_root_abs) or "recordings"

        super().__init__(
            name=self.__class__.__name__,
            root=root,
            cleaner_cfg=cleaner_cfg,
            default_target_dirs=[default_target],
            default_file_extensions=self.DEFAULT_FILE_EXTENSIONS,
            # 녹화 세션 폴더(<ts>_<video>/, frames/) 는 세션마다 새로 만들어지므로
            # 비면 같이 정리되는 게 자연스럽다 (다음 녹화 시 makedirs 로 재생성).
            default_remove_empty_dirs=True,
        )
