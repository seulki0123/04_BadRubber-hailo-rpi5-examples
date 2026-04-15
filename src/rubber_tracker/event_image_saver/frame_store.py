"""
FrameStore — 스레드 안전한 최신 프레임 + 활성 트랙 bbox 저장소.

ImageEventCapture가 on_updated 호출 시마다 업데이트하며,
EventImageSaver가 이벤트 발생 시 snapshot()으로 원자적으로 읽어갑니다.
"""

import threading
from typing import Any, Dict, Optional, Tuple

import numpy as np


class FrameStore:
    """
    최신 video frame 1장과, 현재 활성 트랙들의 bbox 맵을 들고 있는
    스레드 안전한 저장소.

    설계 특징:
    - 프레임은 1개만 유지 (모든 트랙이 같은 video frame을 공유하므로).
    - bbox는 track_id 별로 유지하여 이벤트 발생 시 특정 객체 강조 가능.
    - snapshot()은 frame의 깊은 복사본을 반환 → 호출자가 안전하게 수정 가능.
    - 락 내부에서 I/O를 수행하지 않음 → 최소 임계구역.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._frame: Optional[np.ndarray] = None
        self._tracks: Dict[int, Dict[str, Any]] = {}

    # ------------------------------------------------------------
    # Writer API (ImageEventCapture가 호출)
    # ------------------------------------------------------------
    def update(self, track_id, bbox, frame=None, age: int = 0) -> None:
        """
        트랙 1개의 bbox와 (있다면) 최신 frame을 반영한다.

        Args:
            track_id: 내부 트랙 ID (정수 or 변환 가능한 값).
            bbox: (x1, y1, x2, y2) 형태.
            frame: numpy 이미지 (H, W, C). None이면 frame은 갱신하지 않음.
            age: 트래커의 age 필드 (선택).
        """
        try:
            tid = int(track_id)
        except (TypeError, ValueError):
            return  # 변환 불가능한 ID는 무시

        try:
            bbox_tuple = tuple(bbox) if bbox is not None else None
        except TypeError:
            bbox_tuple = None

        try:
            age_int = int(age) if age is not None else 0
        except (TypeError, ValueError):
            age_int = 0

        with self._lock:
            if frame is not None:
                self._frame = frame
            self._tracks[tid] = {
                "bbox": bbox_tuple,
                "age": age_int,
            }

    def remove(self, track_id) -> None:
        """특정 트랙의 bbox 캐시를 제거한다 (on_removed 후 호출)."""
        try:
            tid = int(track_id)
        except (TypeError, ValueError):
            return
        with self._lock:
            self._tracks.pop(tid, None)

    # ------------------------------------------------------------
    # Reader API (EventImageSaver가 호출)
    # ------------------------------------------------------------
    def snapshot(self) -> Tuple[Optional[np.ndarray], Dict[int, Dict[str, Any]]]:
        """
        현재 frame의 깊은 복사본과 tracks 스냅샷을 반환한다.

        Returns:
            (frame_copy, tracks_copy). frame이 한 번도 들어오지 않았으면 (None, {}).
        """
        with self._lock:
            frame = self._frame
            tracks_copy = {k: dict(v) for k, v in self._tracks.items()}

        # numpy copy는 락 밖에서 (큰 배열 복사가 길어질 수 있으므로)
        if frame is None:
            return None, tracks_copy
        try:
            frame_copy = frame.copy()
        except Exception:
            # 복사 실패 시에도 파이프라인은 멈추지 않아야 함
            frame_copy = None
        return frame_copy, tracks_copy

    def get_bbox(self, track_id) -> Optional[Tuple[int, int, int, int]]:
        """단일 트랙의 bbox만 조회 (복사 없는 가벼운 조회)."""
        try:
            tid = int(track_id)
        except (TypeError, ValueError):
            return None
        with self._lock:
            entry = self._tracks.get(tid)
            return entry["bbox"] if entry else None

    def size(self) -> int:
        """현재 캐시된 트랙 수 (모니터링 용)."""
        with self._lock:
            return len(self._tracks)
