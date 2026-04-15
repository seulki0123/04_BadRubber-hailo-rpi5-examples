"""
Event Image Saver module.

트래킹 이벤트(created, weigher_in/out, final_baler, exited, removed 등)마다
현재 프레임을 디스크에 저장합니다.

설계 원칙:
- 기존 코드를 수정하지 않음 (run.py 5줄 추가만 필요).
- 저장 작업은 별도 워커 스레드에서 비동기 수행 → 메인 파이프라인 블로킹 없음.
- 모든 예외는 내부에서 흡수 → 다른 콜백/파이프라인에 영향 차단.
- 기본 disabled. config의 event_image_saver.enabled=true 시 동작.

Usage (in app/run.py):
    from rubber_tracker.event_image_saver import (
        FrameStore, ImageEventCapture, EventImageSaver,
    )

    frame_store = FrameStore()
    image_saver = EventImageSaver(frame_store)
    wrapped_handler = ImageEventCapture(TrackEventHandler(track_manager), frame_store)

    app.create_pipeline(..., wrapped_handler, ...)
    track_manager.add_callback(image_saver.on_event)
    image_saver.start()
"""

from .frame_store import FrameStore
from .event_capture import ImageEventCapture
from .saver import EventImageSaver

__all__ = ["FrameStore", "ImageEventCapture", "EventImageSaver"]
