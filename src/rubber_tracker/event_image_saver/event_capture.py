"""
ImageEventCapture — 기존 TrackEventHandler를 wrapping 하는 Decorator.

원본 TrackEventHandler의 동작은 100% 그대로 유지하며, on_updated 시점에
FrameStore에 프레임을 캐싱만 추가합니다. 캐싱은 inner handler 호출 "전에"
수행되어, 내부에서 emit되는 이벤트(weigher_in, weigher_out, final_baler 등)가
최신 프레임을 참조할 수 있게 합니다.
"""

from typing import Any

from .frame_store import FrameStore


class ImageEventCapture:
    """
    TrackEventHandler 인터페이스 (on_created / on_updated / on_removed) 를
    그대로 구현하는 투명한 Decorator.

    Contract:
      - 원본 handler가 받던 인자 조합/호출 순서 그대로 전달한다.
      - frame 캐싱 외에는 어떤 side-effect도 추가하지 않는다.
      - 예외는 삼키지 않는다 (원본과 동일한 장애 동작 유지).
    """

    def __init__(self, inner_handler: Any, frame_store: FrameStore):
        if inner_handler is None:
            raise ValueError("inner_handler must not be None")
        if frame_store is None:
            raise ValueError("frame_store must not be None")
        self._inner = inner_handler
        self._frame_store = frame_store

    # -----------------------------------------------------------
    def on_created(self, track_id, bbox, conf):
        # 생성 시점에는 frame이 handler에 전달되지 않음 → bbox만 캐싱.
        # frame은 다음 on_updated에서 채워짐.
        self._frame_store.update(track_id, bbox, frame=None)
        self._inner.on_created(track_id, bbox, conf)

    def on_updated(self, track_id, bbox, frame, age):
        # 핵심: inner 호출 "전"에 프레임을 캐싱한다.
        # inner 내부에서 weigher_in/out 등 이벤트가 emit될 때 최신 프레임 조회 가능.
        self._frame_store.update(track_id, bbox, frame=frame, age=age)
        self._inner.on_updated(track_id, bbox, frame, age)

    def on_removed(self, track_id, bbox, age):
        # "removed"/"exited" 이벤트는 inner 내부에서 emit된다.
        # 그 순간엔 bbox 캐시가 살아있어야 하므로, inner 호출 "후"에 정리한다.
        self._inner.on_removed(track_id, bbox, age)
        self._frame_store.remove(track_id)
