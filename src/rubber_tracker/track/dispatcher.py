"""
TrackDispatcher — 단일 DetectionPipeline 출력(track 이벤트)을
프레임 내 bbox Y 위치 기준으로 여러 TrackManager 에 라우팅한다.

배경:
    IPCamera 가 두 카메라를 세로로 이어붙여 단일 프레임을 만들고, 단일
    Hailo NPU 가 그 위에서 detect → 단일 Tracker 가 track_id 를 부여한다.
    각 카메라(=프로파일)가 독립적으로 동작하는 것처럼 보이려면 그 단일 출력을
    프로파일별 TrackManager 로 fan-out 해야 한다. 이때 어떤 track 이 어느
    프로파일 소속인지는 bbox 의 세로 위치로 판단한다.

프레임 레이아웃 (IPCamera 가 만드는 합성 프레임):
    rows [0,             cam_h)            → profile[0]  (cam1 / 위)
    rows [cam_h,         cam_h + blank)    → 빈 영역 (무시)
    rows [cam_h + blank, 2*cam_h + blank)  → profile[1]  (cam2 / 아래)

단일 프로파일 모드 (len(managers) == 1):
    모든 track 을 profile[0] 으로만 보낸다 (passthrough).

이벤트 흐름:
    on_created  → 어느 프로파일인지 결정 → track_id ↔ manager 매핑 기억
    on_updated  → 매핑된 manager 에게만 전달 (없으면 무시)
    on_removed  → 매핑된 manager 에게만 전달 후 매핑 정리
"""

import threading


class TrackDispatcher:
    """Routes detection events to per-profile TrackManagers by bbox Y-band.

    Args:
        managers: 프로파일 순서대로 정렬된 TrackManager 리스트.
                  index 0 → 위쪽 카메라(cam1), index 1 → 아래쪽 카메라(cam2).
        cam_h: 단일 카메라의 프레임 높이 (= IPCamera.cfg_h).
        blank: 두 카메라 사이의 빈 영역 픽셀 수 (= IPCamera.blank).
        logger: 선택적 logger (호출자의 ProcessLogger). 없으면 print 로 폴백.
    """

    def __init__(self, managers, cam_h, blank, logger=None):
        if not managers:
            raise ValueError("TrackDispatcher: managers 가 비어있습니다.")
        if len(managers) > 2:
            raise ValueError(
                f"TrackDispatcher: 최대 2개 프로파일만 지원 (got {len(managers)})."
            )

        self._managers = list(managers)
        self._cam_h = int(cam_h)
        self._blank = int(blank)
        self._logger = logger

        self._lock = threading.Lock()
        self._track_to_idx = {}  # track_id -> manager index

    # ------------------------------------------------------------
    # Routing
    # ------------------------------------------------------------
    def _which_manager(self, bbox):
        """bbox 의 중심 Y 좌표로 어느 프로파일에 속하는지 결정한다."""
        if len(self._managers) == 1:
            return 0

        try:
            _, y1, _, y2 = bbox[:4]
            cy = (float(y1) + float(y2)) / 2.0
        except Exception:
            return None

        if cy < self._cam_h:
            return 0
        if cy < self._cam_h + self._blank:
            return None  # 두 카메라 사이의 빈 영역
        if cy < 2 * self._cam_h + self._blank:
            return 1
        return None

    def _log_warning(self, msg):
        if self._logger is not None:
            try:
                self._logger.log_warning(msg)
                return
            except Exception:
                pass
        print(f"[TrackDispatcher][WARN] {msg}")

    # ------------------------------------------------------------
    # Event handler interface (DetectionPipeline 가 호출)
    # ------------------------------------------------------------
    def can_create_track(self, bbox):
        idx = self._which_manager(bbox)
        if idx is None:
            return False
        return self._managers[idx].can_create_track(bbox)

    def on_created(self, track_id, bbox, conf):
        idx = self._which_manager(bbox)
        if idx is None:
            self._log_warning(
                f"on_created: track {track_id} bbox={bbox} 가 어느 프로파일에도 속하지 않음 — 무시"
            )
            return

        with self._lock:
            self._track_to_idx[int(track_id)] = idx

        self._managers[idx].on_created(track_id, bbox, conf)

    def on_updated(self, track_id, bbox, frame, age):
        with self._lock:
            idx = self._track_to_idx.get(int(track_id))

        if idx is None:
            # on_created 에서 무시된 트랙은 update 에서도 무시한다.
            return

        self._managers[idx].on_updated(track_id, bbox, frame, age)

    def on_removed(self, track_id, bbox, age):
        with self._lock:
            idx = self._track_to_idx.pop(int(track_id), None)

        if idx is None:
            return

        self._managers[idx].on_removed(track_id, bbox, age)

    # ------------------------------------------------------------
    # 진단
    # ------------------------------------------------------------
    def stats(self):
        with self._lock:
            counts = [0] * len(self._managers)
            for idx in self._track_to_idx.values():
                if 0 <= idx < len(counts):
                    counts[idx] += 1
            return {"per_profile_active_tracks": counts}
