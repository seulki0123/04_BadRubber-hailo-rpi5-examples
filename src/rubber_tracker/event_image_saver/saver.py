"""
EventImageSaver — 트래킹 이벤트 발생 시 현재 프레임을 이미지 파일로 저장.

동작 방식:
  1. track_manager.add_callback(saver.on_event) 로 등록됨.
  2. on_event(evt) 호출 시 FrameStore.snapshot()으로 현재 프레임 가져옴.
  3. 실제 파일 저장은 비동기 워커 스레드에서 수행 (메인 파이프라인 블로킹 방지).
  4. 모든 예외는 내부에서 흡수 → 다른 콜백/파이프라인에 영향 없음.

이벤트 타입 예시 (event_service.py 기준):
  - id_added_{zone}
  - created_{zone}
  - weigher_in_{zone}
  - weigher_out_{zone}
  - final_baler_{zone}
  - exited_{zone}
  - removed_{zone}
"""

import os
import re
import queue
import threading
from datetime import datetime
from typing import Any, Dict, Optional, Set

import cv2
import numpy as np

from rubber_tracker.utils import ProcessLogger, CustomThread, load_config

from .frame_store import FrameStore


# ----- 파일명 안전 변환용 정규식 -----
# 한글/영문/숫자/언더스코어/점/하이픈/콜론 외 모두 "_"로 치환
_SAFE_CHARS_RE = re.compile(r"[^a-zA-Z0-9가-힣_.\-]")
_MAX_PART_LEN = 60


def _safe_filename_part(value: Any) -> str:
    """파일명에 쓸 수 있도록 문자열 정제 + 길이 제한."""
    s = str(value) if value is not None else "none"
    s = _SAFE_CHARS_RE.sub("_", s)
    if len(s) > _MAX_PART_LEN:
        s = s[:_MAX_PART_LEN]
    return s or "empty"


class EventImageSaver(ProcessLogger):
    """
    트래킹 이벤트마다 현재 프레임을 디스크에 저장하는 서비스.

    라이프사이클:
        saver = EventImageSaver(frame_store)
        saver.start()                               # 워커 스레드 기동
        track_manager.add_callback(saver.on_event)  # 콜백 등록
        ... 운영 ...
        saver.stop()                                # 종료 시

    주요 설정 (config.event_image_saver.*):
        enabled:                 (bool) 기본 False. True 시에만 실제 저장.
        save_dir:                (str)  저장 루트. 기본 "results/event_images".
        draw_bbox:               (bool) bbox 주석 포함 여부. 기본 True.
        draw_all_tracks:         (bool) 모든 활성 트랙 표시. 기본 True.
        organize_by_event_type:  (bool) 이벤트 타입별 하위 폴더 구성. 기본 True.
        queue_size:              (int)  비동기 큐 크기. 기본 500.
        jpeg_quality:            (int)  JPEG 품질 1~100. 기본 90.
        enabled_event_prefixes:  (list|null) null이면 전체. 리스트면 해당 접두사만.
    """

    # 안전 기본값
    _DEFAULTS = {
        "enabled": False,
        "save_dir": "results/event_images",
        "draw_bbox": True,
        "draw_all_tracks": True,
        "organize_by_event_type": True,
        "queue_size": 500,
        "jpeg_quality": 90,
        "enabled_event_prefixes": None,
    }

    def __init__(self, frame_store: FrameStore, config: Optional[Dict[str, Any]] = None):
        super().__init__(self.__class__.__name__)

        if frame_store is None:
            raise ValueError("frame_store must not be None")
        self._frame_store = frame_store

        # config 병합: 파일 config → self._DEFAULTS 순서로 fallback
        cfg: Dict[str, Any] = {}
        if config is None:
            try:
                cfg = (load_config() or {}).get("event_image_saver", {}) or {}
            except Exception as e:
                # config 로드 실패 시에도 기본값으로 진행
                self.log_warning(f"Failed to load config, using defaults: {e}")
                cfg = {}
        else:
            cfg = dict(config)

        def _cfg(key, cast=None):
            value = cfg.get(key, self._DEFAULTS[key])
            if cast is not None and value is not None:
                try:
                    value = cast(value)
                except (TypeError, ValueError):
                    value = self._DEFAULTS[key]
            return value

        self._enabled: bool = bool(_cfg("enabled"))
        self._save_dir: str = str(_cfg("save_dir"))
        self._draw_bbox: bool = bool(_cfg("draw_bbox"))
        self._draw_all_tracks: bool = bool(_cfg("draw_all_tracks"))
        self._organize_by_event_type: bool = bool(_cfg("organize_by_event_type"))
        self._queue_size: int = max(1, _cfg("queue_size", int))
        self._jpeg_quality: int = int(np.clip(_cfg("jpeg_quality", int), 1, 100))

        prefixes = cfg.get("enabled_event_prefixes", None)
        if prefixes is not None and not isinstance(prefixes, (list, tuple, set)):
            self.log_warning(
                f"enabled_event_prefixes must be a list, got {type(prefixes).__name__}. Ignoring."
            )
            prefixes = None
        self._enabled_prefixes: Optional[Set[str]] = (
            {str(p) for p in prefixes} if prefixes else None
        )

        self._save_queue: "queue.Queue[dict]" = queue.Queue(maxsize=self._queue_size)
        self._worker: Optional[CustomThread] = None
        self._stop_flag = threading.Event()
        self._drops_count: int = 0
        self._saved_count: int = 0

    # ================================================================
    # Lifecycle
    # ================================================================
    def start(self) -> None:
        """워커 스레드를 기동한다. enabled=False 면 no-op."""
        if not self._enabled:
            self.log_info("EventImageSaver disabled (config.event_image_saver.enabled=false)")
            return

        # save_dir 생성 실패 시 자동 disable (크래시 대신 graceful degradation)
        try:
            os.makedirs(self._save_dir, exist_ok=True)
        except Exception as e:
            self.log_error(
                f"Cannot create save_dir '{self._save_dir}': {e}. Disabling saver."
            )
            self._enabled = False
            return

        if self._worker is not None:
            self.log_warning("EventImageSaver already started")
            return

        self._worker = CustomThread(
            name=self.__class__.__name__ + "_worker",
            task=self._worker_task,
            interval=0,
        )
        self._worker.start()

        filter_desc = "ALL" if self._enabled_prefixes is None else sorted(self._enabled_prefixes)
        self.log_info(
            f"EventImageSaver started | save_dir={self._save_dir} | "
            f"filters={filter_desc} | queue_size={self._queue_size} | "
            f"draw_bbox={self._draw_bbox} | jpeg_quality={self._jpeg_quality}"
        )

    def stop(self) -> None:
        """워커 스레드를 정지한다."""
        self._stop_flag.set()
        if self._worker is not None:
            try:
                self._worker.stop()
            except Exception as e:
                self.log_warning(f"stop error: {e}")
            self._worker = None
        self.log_info(
            f"EventImageSaver stopped | saved={self._saved_count} | drops={self._drops_count}"
        )

    # ================================================================
    # Event callback (TrackManager.add_callback(...) 로 등록)
    # ================================================================
    def on_event(self, evt: Optional[dict]) -> None:
        """
        트래킹 이벤트 수신 콜백.
        절대 예외를 전파하지 않는다 (다른 콜백/파이프라인 보호).
        """
        try:
            self._handle(evt)
        except Exception as e:
            # 방어 최후 방어선. 여기까지 오면 안됨.
            try:
                self.log_error(f"on_event unhandled: {e}")
            except Exception:
                pass

    def _handle(self, evt: Optional[dict]) -> None:
        if not self._enabled:
            return
        if evt is None or not isinstance(evt, dict):
            return

        event_type = evt.get("event")
        if not event_type or not isinstance(event_type, str):
            return

        # 이벤트 타입 필터
        if self._enabled_prefixes is not None:
            if not any(event_type.startswith(p) for p in self._enabled_prefixes):
                return

        # 현재 프레임 스냅샷
        frame, tracks = self._frame_store.snapshot()
        if frame is None:
            # 초기화 직후(아직 첫 프레임 미도착) 등 → skip
            return

        # 큐에 enqueue (non-blocking)
        item = {
            "frame": frame,
            "tracks": tracks,
            "evt": dict(evt),  # 외부 수정에 대한 방어
        }
        try:
            self._save_queue.put_nowait(item)
        except queue.Full:
            self._drops_count += 1
            if self._drops_count % 100 == 1:
                self.log_warning(
                    f"Save queue full. Dropping event. total_drops={self._drops_count}"
                )

    # ================================================================
    # Worker
    # ================================================================
    def _worker_task(self) -> None:
        if self._stop_flag.is_set():
            return
        try:
            item = self._save_queue.get(timeout=0.1)
        except queue.Empty:
            return

        try:
            self._save_one(item)
            self._saved_count += 1
        except Exception as e:
            try:
                self.log_error(f"save_one error: {e}")
            except Exception:
                pass

    def _save_one(self, item: dict) -> None:
        frame: np.ndarray = item["frame"]
        tracks: Dict[int, Dict[str, Any]] = item["tracks"]
        evt: dict = item["evt"]

        # 메타 추출
        event_type = str(evt.get("event", "unknown"))
        ext_id = evt.get("id", "unknown")
        zone = evt.get("zone") or "none"
        rejected = bool(evt.get("rejected", False))

        # 타임스탬프 (초 + ms)
        now = datetime.now()
        ts_str = now.strftime("%Y%m%d_%H%M%S") + f"_{now.microsecond // 1000:03d}"

        # 파일명 구성
        name_parts = [
            ts_str,
            _safe_filename_part(event_type),
            _safe_filename_part(ext_id),
        ]
        if rejected:
            name_parts.append("REJECTED")
        filename = "_".join(name_parts) + ".jpg"

        # 저장 디렉토리 (이벤트 타입별 하위 폴더 옵션)
        if self._organize_by_event_type:
            # "weigher_in_zoneA" → 폴더명 "weigher_in" (앞 두 단어)
            parts = event_type.split("_")
            folder_name = "_".join(parts[:2]) if len(parts) >= 2 else event_type
            folder_name = _safe_filename_part(folder_name) or "misc"
            subdir = os.path.join(self._save_dir, folder_name)
        else:
            subdir = self._save_dir

        try:
            os.makedirs(subdir, exist_ok=True)
        except Exception as e:
            self.log_error(f"makedirs failed ({subdir}): {e}")
            return

        save_path = os.path.join(subdir, filename)

        # 이미지 준비 (draw_bbox/주석)
        img = self._prepare_image(frame, tracks, evt)

        # 저장
        try:
            ok = cv2.imwrite(
                save_path,
                img,
                [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality],
            )
            if not ok:
                self.log_error(f"cv2.imwrite returned False: {save_path}")
        except Exception as e:
            self.log_error(f"cv2.imwrite exception ({save_path}): {e}")

    # ================================================================
    # Drawing helpers
    # ================================================================
    def _prepare_image(
        self,
        frame: np.ndarray,
        tracks: Dict[int, Dict[str, Any]],
        evt: dict,
    ) -> np.ndarray:
        """bbox 주석 및 이벤트 라벨을 그린 이미지를 반환.
        실패 시 원본 프레임을 그대로 반환."""
        try:
            if not self._draw_bbox:
                return frame

            # frame이 이미 복사본이므로(FrameStore.snapshot 에서 copy) 바로 그릴 수 있음
            img = frame

            # 모든 활성 트랙 bbox (연회색)
            if self._draw_all_tracks and tracks:
                for tid, info in tracks.items():
                    bbox = info.get("bbox")
                    if bbox is None or len(bbox) < 4:
                        continue
                    self._draw_box(img, bbox, color=(150, 150, 150), thickness=1, label=f"#{tid}")

            # 이벤트 라벨 (상단 오버레이)
            self._draw_event_label(img, evt)

            return img
        except Exception as e:
            try:
                self.log_warning(f"prepare_image error: {e}")
            except Exception:
                pass
            return frame

    def _draw_box(self, img, bbox, color=(0, 255, 0), thickness=2, label: str = "") -> None:
        try:
            x1, y1, x2, y2 = (int(v) for v in bbox[:4])
            h, w = img.shape[:2]
            x1 = max(0, min(w - 1, x1))
            y1 = max(0, min(h - 1, y1))
            x2 = max(0, min(w - 1, x2))
            y2 = max(0, min(h - 1, y2))
            cv2.rectangle(img, (x1, y1), (x2, y2), color, thickness)
            if label:
                font = cv2.FONT_HERSHEY_SIMPLEX
                scale = 0.4
                t = 1
                (tw, th), _ = cv2.getTextSize(label, font, scale, t)
                ty = max(th + 3, y1 - 3)
                cv2.putText(img, label, (x1 + 2, ty), font, scale, color, t, cv2.LINE_AA)
        except Exception:
            pass  # 드로잉 실패는 치명적 아님

    def _draw_event_label(self, img, evt: dict) -> None:
        try:
            event_type = str(evt.get("event", ""))
            ext_id = str(evt.get("id", ""))
            zone = str(evt.get("zone") or "")
            rejected = bool(evt.get("rejected", False))
            baler = evt.get("baler")
            final_baler = evt.get("final_baler")

            parts = [event_type, f"id={ext_id}", f"zone={zone}"]
            if baler is not None:
                parts.append(f"baler={baler}")
            if final_baler is not None:
                parts.append(f"final={final_baler}")
            if rejected:
                parts.append("REJECTED")
            label = " | ".join(parts)

            font = cv2.FONT_HERSHEY_SIMPLEX
            scale = 0.5
            thickness = 1
            (tw, th), bl = cv2.getTextSize(label, font, scale, thickness)

            h, w = img.shape[:2]
            margin = 8
            x = margin
            y = margin + th

            bg_color = (0, 0, 180) if rejected else (0, 160, 0)  # BGR
            cv2.rectangle(
                img,
                (x - 4, y - th - 4),
                (min(w - 1, x + tw + 4), y + bl + 4),
                bg_color,
                -1,
            )
            cv2.putText(img, label, (x, y), font, scale, (255, 255, 255), thickness, cv2.LINE_AA)
        except Exception:
            pass
