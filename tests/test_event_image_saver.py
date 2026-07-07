"""
Unit tests for event_image_saver module.

실행:
    cd 프로젝트루트
    PYTHONPATH=src python -m pytest tests/test_event_image_saver.py -v

이 테스트는 외부 의존성(Hailo NPU, GStreamer, IP 카메라) 없이
event_image_saver 모듈의 동작만 독립 검증한다.

주의: 이 테스트는 rubber_tracker.utils.load_config 를 임포트하므로,
config/base.yaml 이 존재하는 경로(프로젝트 루트)에서 실행되어야 한다.
"""

import os
import sys
import time
import threading
import numpy as np
import pytest
from unittest.mock import MagicMock


# -----------------------------------------------------------------
# 모듈 임포트 (프로젝트 src/ 경로가 sys.path에 있어야 함)
# -----------------------------------------------------------------
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC_PATH = os.path.join(PROJECT_ROOT, "src")
if SRC_PATH not in sys.path:
    sys.path.insert(0, SRC_PATH)

from rubber_tracker.event_image_saver import FrameStore, ImageEventCapture, EventImageSaver


# =================================================================
# FrameStore
# =================================================================
class TestFrameStore:
    def test_initial_state(self):
        store = FrameStore()
        frame, tracks = store.snapshot()
        assert frame is None
        assert tracks == {}

    def test_update_and_snapshot(self):
        store = FrameStore()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        store.update(track_id=1, bbox=(10, 20, 30, 40), frame=frame, age=5)

        snap_frame, snap_tracks = store.snapshot()
        assert snap_frame is not None
        assert snap_frame.shape == (100, 100, 3)
        assert 1 in snap_tracks
        assert snap_tracks[1]["bbox"] == (10, 20, 30, 40)
        assert snap_tracks[1]["age"] == 5

    def test_update_without_frame_keeps_frame(self):
        """bbox만 업데이트할 때 기존 frame은 유지되어야 한다."""
        store = FrameStore()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        store.update(1, (0, 0, 10, 10), frame)
        store.update(2, (20, 20, 30, 30), None)

        snap_frame, snap_tracks = store.snapshot()
        assert snap_frame is not None  # 유지됨
        assert 1 in snap_tracks
        assert 2 in snap_tracks

    def test_remove(self):
        store = FrameStore()
        store.update(1, (0, 0, 10, 10), np.zeros((10, 10, 3), dtype=np.uint8))
        store.remove(1)
        _, tracks = store.snapshot()
        assert 1 not in tracks

    def test_snapshot_returns_deep_copy(self):
        """snapshot 후 복사본을 수정해도 원본에 영향 없어야 한다."""
        store = FrameStore()
        frame = np.zeros((100, 100, 3), dtype=np.uint8)
        store.update(1, (0, 0, 10, 10), frame)

        snap_frame, _ = store.snapshot()
        snap_frame[0, 0] = [255, 255, 255]  # 복사본 수정

        snap_frame2, _ = store.snapshot()
        assert snap_frame2[0, 0].tolist() == [0, 0, 0]  # 원본 유지

    def test_invalid_track_id_ignored(self):
        """변환 불가능한 track_id는 무시되어야 한다 (크래시 X)."""
        store = FrameStore()
        store.update("abc", (0, 0, 10, 10), None)   # int 변환 불가
        store.update(None, (0, 0, 10, 10), None)    # None
        store.remove("xyz")                         # 제거도 무시
        _, tracks = store.snapshot()
        assert tracks == {}

    def test_get_bbox(self):
        store = FrameStore()
        store.update(42, (1, 2, 3, 4), np.zeros((5, 5, 3), dtype=np.uint8))
        assert store.get_bbox(42) == (1, 2, 3, 4)
        assert store.get_bbox(999) is None

    def test_size(self):
        store = FrameStore()
        assert store.size() == 0
        for i in range(5):
            store.update(i, (0, 0, 10, 10), None)
        assert store.size() == 5

    def test_thread_safety_stress(self):
        """다중 writer/reader 동시 접근 시 예외 없이 종료하는지."""
        store = FrameStore()

        def writer():
            for i in range(500):
                frame = np.zeros((20, 20, 3), dtype=np.uint8)
                store.update(i % 10, (0, 0, 5, 5), frame, age=i)

        def reader():
            for _ in range(500):
                store.snapshot()

        def remover():
            for i in range(500):
                store.remove(i % 10)

        threads = (
            [threading.Thread(target=writer) for _ in range(3)]
            + [threading.Thread(target=reader) for _ in range(3)]
            + [threading.Thread(target=remover) for _ in range(2)]
        )
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        # 예외 없이 끝났으면 성공


# =================================================================
# ImageEventCapture
# =================================================================
class TestImageEventCapture:
    def test_delegates_on_created(self):
        store = FrameStore()
        inner = MagicMock()
        wrapper = ImageEventCapture(inner, store)
        wrapper.on_created(1, (0, 0, 10, 10), 0.9)
        inner.on_created.assert_called_once_with(1, (0, 0, 10, 10), 0.9)

    def test_delegates_on_updated(self):
        store = FrameStore()
        inner = MagicMock()
        wrapper = ImageEventCapture(inner, store)
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        wrapper.on_updated(1, (0, 0, 10, 10), frame, age=3)
        inner.on_updated.assert_called_once_with(1, (0, 0, 10, 10), frame, 3)

    def test_delegates_on_removed(self):
        store = FrameStore()
        inner = MagicMock()
        wrapper = ImageEventCapture(inner, store)
        wrapper.on_removed(1, (0, 0, 10, 10), 5)
        inner.on_removed.assert_called_once_with(1, (0, 0, 10, 10), 5)

    def test_on_updated_caches_before_inner_call(self):
        """inner handler 호출 시점에 이미 frame이 캐시되어 있어야 한다
        (inner 내부에서 이벤트가 emit되어도 최신 frame 참조 가능)."""
        store = FrameStore()
        cached_during_inner = {}

        def inner_on_updated(track_id, bbox, frame, age):
            snap_frame, _ = store.snapshot()
            cached_during_inner["frame_visible"] = snap_frame is not None

        inner = MagicMock()
        inner.on_updated.side_effect = inner_on_updated

        wrapper = ImageEventCapture(inner, store)
        frame = np.ones((10, 10, 3), dtype=np.uint8) * 77
        wrapper.on_updated(1, (0, 0, 10, 10), frame, 3)

        assert cached_during_inner["frame_visible"] is True

    def test_on_removed_cleans_cache_after_inner(self):
        """on_removed: inner handler 호출이 먼저, 그 다음에 캐시 정리."""
        store = FrameStore()
        cached_during_inner = {}

        def inner_on_removed(track_id, bbox, age):
            cached_during_inner["bbox_visible"] = store.get_bbox(track_id) is not None

        inner = MagicMock()
        inner.on_removed.side_effect = inner_on_removed

        wrapper = ImageEventCapture(inner, store)
        frame = np.zeros((10, 10, 3), dtype=np.uint8)
        wrapper.on_updated(1, (0, 0, 10, 10), frame, 3)
        wrapper.on_removed(1, (0, 0, 10, 10), 3)

        assert cached_during_inner["bbox_visible"] is True  # inner 내부에선 아직 살아있음
        _, tracks = store.snapshot()
        assert 1 not in tracks  # inner 이후엔 제거됨

    def test_raises_on_invalid_init(self):
        with pytest.raises(ValueError):
            ImageEventCapture(None, FrameStore())
        with pytest.raises(ValueError):
            ImageEventCapture(MagicMock(), None)


# =================================================================
# EventImageSaver
# =================================================================
class TestEventImageSaver:
    def _make_saver(self, tmp_path, **overrides):
        cfg = {
            "enabled": True,
            "save_dir": str(tmp_path),
            "draw_bbox": False,  # 테스트에서 기본 off (속도/단순성)
            "draw_all_tracks": False,
            "organize_by_event_type": True,
            "queue_size": 100,
            "jpeg_quality": 80,
            "enabled_event_prefixes": None,
            "frame_buffer_size": 1,
            "pre_event_frames": 0,
            "post_event_frames": 0,
            "max_pending_events": 50,
            "max_events_per_day": 1000,
        }
        cfg.update(overrides)
        return EventImageSaver(FrameStore(), cfg)

    def test_disabled_does_not_save(self, tmp_path):
        saver = self._make_saver(tmp_path, enabled=False)
        saver.start()
        saver.on_event({"type": "weigher_in_zoneA", "id": "X"})
        time.sleep(0.2)
        saver.stop()
        assert not list(tmp_path.rglob("*.jpg"))

    def test_frame_buffer_size_must_cover_event_window(self, tmp_path):
        with pytest.raises(ValueError):
            self._make_saver(
                tmp_path,
                frame_buffer_size=20,
                pre_event_frames=10,
                post_event_frames=10,
            )

    def test_event_without_cached_frame_skipped(self, tmp_path):
        """FrameStore에 frame이 없으면 저장 스킵 (초기화 직후 케이스)."""
        saver = self._make_saver(tmp_path)
        saver.start()
        saver.on_event({"type": "weigher_in_zoneA", "id": "X"})
        time.sleep(0.3)
        saver.stop()
        assert not list(tmp_path.rglob("*.jpg"))

    def test_saves_with_cached_frame(self, tmp_path):
        saver = self._make_saver(tmp_path)
        # FrameStore에 frame 직접 주입
        saver._frames.update(1, (5, 5, 15, 15),
                             np.ones((30, 30, 3), dtype=np.uint8) * 128)
        saver.start()
        saver.on_event({
            "type": "weigher_in_zoneA",
            "id": "testid_123",
            "zone": "zoneA",
            "rejected": False,
        })
        # 워커가 처리할 시간
        for _ in range(20):
            files = list(tmp_path.rglob("*.jpg"))
            if files:
                break
            time.sleep(0.05)
        saver.stop()

        files = list(tmp_path.rglob("*.jpg"))
        assert len(files) >= 1
        name = str(files[0])
        assert "weigher_in" in name
        assert "testid_123" in name
        assert "_event.jpg" in files[0].name
        assert files[0].with_suffix(".txt").read_text().strip() == "0 0.333333 0.333333 0.333333 0.333333"

    def test_organize_by_event_type_creates_subdirs(self, tmp_path):
        saver = self._make_saver(tmp_path, organize_by_event_type=True)
        saver._frames.update(1, (0, 0, 5, 5),
                             np.zeros((10, 10, 3), dtype=np.uint8))
        saver.start()
        saver.on_event({"type": "weigher_in_zoneA", "id": "A", "zone": "zoneA"})
        saver.on_event({"type": "final_baler_house_in_a", "id": "B", "zone": "house_in_a"})
        for _ in range(30):
            if len(list(tmp_path.rglob("*.jpg"))) >= 2:
                break
            time.sleep(0.05)
        saver.stop()

        date_dirs = [p for p in tmp_path.iterdir() if p.is_dir()]
        assert len(date_dirs) == 1
        subdirs = {p.name for p in date_dirs[0].iterdir() if p.is_dir()}
        assert "weigher_in" in subdirs
        assert "final_baler" in subdirs

    def test_prefix_filter(self, tmp_path):
        saver = self._make_saver(
            tmp_path,
            enabled_event_prefixes=["weigher_in"],
        )
        saver._frames.update(1, (0, 0, 5, 5),
                             np.zeros((10, 10, 3), dtype=np.uint8))
        saver.start()
        saver.on_event({"type": "created_zoneA", "id": "A"})        # 필터 아웃
        saver.on_event({"type": "weigher_in_zoneA", "id": "B"})     # 통과
        for _ in range(20):
            if list(tmp_path.rglob("*.jpg")):
                break
            time.sleep(0.05)
        saver.stop()

        files = [str(f) for f in tmp_path.rglob("*.jpg")]
        assert any("weigher_in" in f for f in files)
        assert not any("/created" in f or "created_zoneA" in f for f in files)

    def test_rejected_event_marker(self, tmp_path):
        saver = self._make_saver(tmp_path)
        saver._frames.update(1, (0, 0, 5, 5),
                             np.zeros((10, 10, 3), dtype=np.uint8))
        saver.start()
        saver.on_event({
            "type": "removed_none",
            "id": "bad_id_1",
            "rejected": True,
        })
        for _ in range(20):
            if list(tmp_path.rglob("*.jpg")):
                break
            time.sleep(0.05)
        saver.stop()

        files = [str(f) for f in tmp_path.rglob("*.jpg")]
        assert any("REJECTED" in f for f in files)

    def test_malformed_events_do_not_crash(self, tmp_path):
        """None, 빈 dict, 비정상 필드 → 예외 없이 무시."""
        saver = self._make_saver(tmp_path)
        saver.start()
        saver.on_event(None)
        saver.on_event({})
        saver.on_event({"type": ""})
        saver.on_event({"type": None})
        saver.on_event({"type": "weigher_in", "id": None})
        saver.on_event({"type": "weigher_in", "id": "X", "rejected": "truthy"})
        time.sleep(0.2)
        saver.stop()
        # 크래시 없이 도달했으면 성공

    def test_queue_overflow_drops_silently(self, tmp_path):
        """큐가 가득 차면 드롭하지만 예외 없이 진행되어야 한다."""
        saver = self._make_saver(tmp_path, queue_size=2)
        saver._frames.update(1, (0, 0, 5, 5),
                             np.zeros((10, 10, 3), dtype=np.uint8))
        saver.start()
        # 워커 스레드가 아직 처리하기 전에 큐를 넘치게 한다
        # (start 후 바로 폭주시키기 — 완벽한 재현은 힘드나 크래시 없음 확인이 목적)
        for i in range(50):
            saver.on_event({"type": "weigher_in", "id": f"X{i}"})
        time.sleep(0.5)
        saver.stop()
        # 드롭 카운터가 올라갔거나, 그대로 동작했거나 둘 다 OK
        # 핵심: 크래시 없음
        assert saver._saved_count + saver._drops_count > 0

    def test_invalid_save_dir_disables_gracefully(self, tmp_path):
        """쓰기 불가능한 save_dir → enabled=False로 graceful degradation."""
        bad_dir = "/proc/nonexistent/readonly/save_dir_xxx"
        saver = self._make_saver(tmp_path, save_dir=bad_dir)
        saver.start()
        assert saver._enabled is False
        saver.stop()


# =================================================================
# 통합: ImageEventCapture + EventImageSaver 엔드투엔드
# =================================================================
class TestIntegration:
    def test_end_to_end_pipeline(self, tmp_path):
        """실제 파이프라인 시나리오 시뮬레이션:
        1. on_created → frame 없음
        2. on_updated → frame 캐시
        3. 이벤트 emit → 이미지 저장
        4. on_removed → 캐시 정리
        """
        store = FrameStore()
        inner = MagicMock()
        wrapper = ImageEventCapture(inner, store)

        saver = EventImageSaver(store, {
            "enabled": True,
            "save_dir": str(tmp_path),
            "draw_bbox": True,          # 주석까지 테스트
            "draw_all_tracks": True,
            "organize_by_event_type": True,
            "queue_size": 100,
            "jpeg_quality": 85,
            "enabled_event_prefixes": None,
            "frame_buffer_size": 1,
            "pre_event_frames": 0,
            "post_event_frames": 0,
            "max_pending_events": 50,
            "max_events_per_day": 1000,
        })
        saver.start()

        # (1) 새 트랙 생성 - frame 없음
        wrapper.on_created(42, (10, 20, 50, 80), 0.95)

        # (2) 업데이트 - frame 캐시됨
        frame = np.random.randint(0, 255, size=(360, 640, 3), dtype=np.uint8)
        wrapper.on_updated(42, (10, 20, 50, 80), frame, age=1)

        # (3) 이벤트 발생 시뮬레이션 (TrackManager가 emit하는 것을 직접 호출)
        saver.on_event({
            "type": "weigher_in_weigher_a",
            "id": "EXT_42",
            "zone": "weigher_a",
            "baler": 2,
            "final_baler": 2,
            "rejected": False,
        })

        # 워커 처리 대기
        for _ in range(40):
            if list(tmp_path.rglob("*.jpg")):
                break
            time.sleep(0.05)

        # (4) 트랙 제거
        wrapper.on_removed(42, (10, 20, 50, 80), 1)
        saver.stop()

        # 검증
        files = list(tmp_path.rglob("*.jpg"))
        assert len(files) >= 1, f"저장된 이미지 없음. tmp={tmp_path}"
        assert "weigher_in" in str(files[0])
        assert "EXT_42" in str(files[0])

        # 실제 이미지가 유효한 JPEG인지 확인
        import cv2
        img = cv2.imread(str(files[0]))
        assert img is not None
        assert img.shape[0] > 0 and img.shape[1] > 0
