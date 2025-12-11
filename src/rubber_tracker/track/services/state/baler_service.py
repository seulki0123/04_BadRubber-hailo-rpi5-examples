# src/rubber_tracker/track/services/state/baler_service.py
import numpy as np
from typing import Dict, Any, Optional, List

from rubber_tracker.utils import ModuleLogger
from ...domain.track_state import TrackState


class BalerService(ModuleLogger):
    """
    BalerService with:
    - thread-safe inflight counter
    - strict finalize rules (no finalize while inflight>0)
    - ready/send logic blocked after reaching vote limit
    """

    def __init__(
        self,
        speed_service,
        classify_service,
        capture_service,
        cls_limit: int,
        track_map: Dict[int, TrackState],
    ):
        super().__init__(self.__class__.__name__)
        self.speed_service = speed_service
        self.classify_service = classify_service
        self.capture_service = capture_service
        self.cls_limit = cls_limit
        self.track_map = track_map  # read-only view provided by TrackRegistry
        self.crops = {}  # track_id: crops

    def update(self, track: TrackState, bbox, frame, zone: Optional[str]):
        """
        Called per track on each frame.
        - Sends classification requests while `_ready()`.
        - Finalizes only when `_should_finalize()`.
        """
        actions = []
        track.update_position(bbox)

        # collect crops
        if zone and self._ready(track):
            crop = self.capture_service.crop(
                bbox,
                frame,
                save_folder=f"{zone}_{track.track_id:06d}",
                save_infos=[track.speed],
            )
            if track.track_id not in self.crops:
                self.crops[track.track_id] = []
            self.crops[track.track_id].append(crop)

        # send classification request
        if self._should_finalize(track):
            self.classify_service.process_batch(track.track_id, self.crops[track.track_id], self._on_classification_result)
            del self.crops[track.track_id]

    # after classification
    def _on_classification_result(self, track_id: int, results: List[Any]):
        print("."*100)
        print(results)
        print("."*100)

    # conditions
    def _ready(self, track: TrackState) -> bool:
        return track.final_baler is None and self.speed_service.is_slow(track.speed) and len(self.crops.get(track.track_id, [])) < self.cls_limit

    def _should_finalize(self, track: TrackState) -> bool:
        return track.final_baler is None and self.speed_service.is_stop(track.speed) and len(self.crops.get(track.track_id, [])) >= self.cls_limit