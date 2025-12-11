# src/rubber_tracker/track/services/state/baler_service.py
import numpy as np
from typing import Dict, Any, Optional, List

from rubber_tracker.utils import ModuleLogger
from ...domain.track_state import TrackState


class BalerService(ModuleLogger):
    def __init__(
        self,
        speed_service,
        classify_service,
        capture_service,
        cls_limit: int,
        cls_conf_threshold: float,
        track_map: Dict[int, TrackState],
        on_baler_finalized=None,
    ):
        super().__init__(self.__class__.__name__)
        self.speed_service = speed_service
        self.classify_service = classify_service
        self.capture_service = capture_service
        self.cls_limit = cls_limit
        self.cls_conf_threshold = cls_conf_threshold
        self.on_baler_finalized = on_baler_finalized
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
            buffer_added = self.classify_service.process_batch(track.track_id, self.crops[track.track_id], self._on_classification_result)
            del self.crops[track.track_id]
            if not buffer_added:
                self._on_classification_result(track.track_id, None, None)

    # after classification
    def _on_classification_result(self, track_id: int, cls_ids, confs):
        # handle None case
        if cls_ids is None or confs is None:
            self.log_error(f"Classification failed for track {track_id}. Using fallback.")

            # finalize with default (0)
            track = self.track_map[track_id]
            track.finalize_baler([])
            if self.on_baler_finalized:
                self.on_baler_finalized(track, "final_baler")
            return
            
        # log raw
        pairs = [(int(cid), round(float(cf), 2)) for cid, cf in zip(cls_ids, confs)]
        self.log_info(f"Classification raw: {pairs}")


        # filter
        cls_ids_np = np.array(cls_ids)
        conf = np.array([float(c) for c in confs])
        cls_ids_np[conf < self.cls_conf_threshold] = 0

        # finalize
        track = self.track_map[track_id]
        track.finalize_baler(cls_ids_np.tolist())
        self.log_info(f"Track '{track.info}' finalized baler as '{track.final_baler}'")

        # emit event
        if self.on_baler_finalized:
            self.on_baler_finalized(track, "final_baler")

    # conditions
    def _ready(self, track: TrackState) -> bool:
        return track.final_baler is None and self.speed_service.is_slow(track.speed) and len(self.crops.get(track.track_id, [])) < self.cls_limit

    def _should_finalize(self, track: TrackState) -> bool:
        return track.final_baler is None and self.speed_service.is_stop(track.speed) and len(self.crops.get(track.track_id, [])) >= self.cls_limit