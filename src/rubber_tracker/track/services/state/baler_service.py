# src/rubber_tracker/track/services/state/baler_service.py
from collections import deque

import numpy as np
from typing import Dict, Any, Optional, List

from rubber_tracker.utils import ProcessLogger
from ...domain.track_state import TrackState


class BalerService(ProcessLogger):
    def __init__(
        self,
        speed_service,
        classify_service,
        capture_service,
        cls_limit: int,
        cls_conf_threshold: float,
        track_map: Dict[int, TrackState],
        on_baler_finalized=None,
        classify_fallback_baler=10,
    ):
        super().__init__(self.__class__.__name__)
        self.speed_service = speed_service
        self.classify_service = classify_service
        self.capture_service = capture_service
        self.cls_limit = cls_limit
        self.cls_conf_threshold = cls_conf_threshold
        self.on_baler_finalized = on_baler_finalized
        self.track_map = track_map  # read-only view provided by TrackRegistry
        self.crops = {
            # "track_id": {
            #     "crops": deque(maxlen=self.cls_limit),
            #     "buffer_added": False,
            # }
        }
        self.classify_fallback_baler = classify_fallback_baler

    def update(self, track: TrackState, bbox, frame, zone: Optional[str]):
        """
        Called per track on each frame.
        - Sends classification requests while `_ready()`.
        - Finalizes only when `_should_finalize()`.
        """
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
                self.crops[track.track_id] = {
                    "crops": deque(maxlen=self.cls_limit),
                    "buffer_added": False,
                }
            self.crops[track.track_id]["crops"].append(crop)
            self.log_info(f"● Crop added: {track.track_id} with {len(self.crops[track.track_id])} crops")

        # send classification request
        if self._should_finalize(track):
            crops = self.crops.get(track.track_id, {}).get("crops", [])
            if not len(crops):
                self._on_classification_result(track.track_id, None, None)
                return

            buffer_added = self.classify_service.process_batch(
                track.track_id,
                list(crops),
                self._on_classification_result
            )
            self.log_info(f"●● Buffer added: {buffer_added} for track {track.track_id}")
            if not buffer_added:
                self._on_classification_result(track.track_id, None, None)
            self.crops[track.track_id]["buffer_added"] = True

    # classifcation callback
    def _on_classification_result(self, track_id: int, cls_ids, confs):
        # track
        track = self.track_map.get(track_id)
        if track is None:
            self.log_error(f"Classification callback after track removed: {track_id}")
            return

        # handle None case
        if cls_ids is None or confs is None:
            self.log_error(f"Classification failed for track {track_id}. Using fallback.")

            # finalize with default (0)
            track.finalize_baler(self.classify_fallback_baler)
            self._on_baler_finalized(track)
            return
            
        # log raw
        pairs = [(int(cid), round(float(cf), 2)) for cid, cf in zip(cls_ids, confs)]
        self.log_info(f"Classification raw: {pairs}")

        # filter
        cls_ids_np = np.array(cls_ids)
        conf = np.array(confs, dtype=float)
        filtered_ids = cls_ids_np[conf >= self.cls_conf_threshold]

        # finalize
        values, counts = [], []
        if len(filtered_ids) == 0:
            baler = self.classify_fallback_baler
        else:
            values, counts = np.unique(filtered_ids, return_counts=True)
            baler = int(values[np.argmax(counts)])

        track.finalize_baler(baler)

        self.log_info(
            f"filtered_ids: {filtered_ids.tolist()}, "
            f"values: {values.tolist()}, counts: {counts.tolist()}, baler: {baler}"
        )

        self._on_baler_finalized(track)
        self.log_info(f"Track '{track.info}' finalized baler, '{track.input_baler}' → '{track.final_baler}'")

    # conditions
    def _ready(self, track: TrackState) -> bool:
        state = self.crops.get(track.track_id)
        if not state:
            return True

        return (
            track.final_baler is None
            and not state["buffer_added"]
            and self.speed_service.is_slow(track.speed)
            and len(state["crops"]) < self.cls_limit
        )

    def _should_finalize(self, track: TrackState) -> bool:
        state = self.crops.get(track.track_id)
        if not state:
            return False

        return (
            track.final_baler is None
            and not state["buffer_added"]
            and (
                self.speed_service.is_stop(track.speed)
                or len(state["crops"]) >= self.cls_limit
            )
        )

    def _on_baler_finalized(self, track: TrackState, event_type="final_baler"):
        if self.on_baler_finalized:
            self.on_baler_finalized(track, event_type=event_type)

    def on_track_removed(self, track_id: int):
        track = self.track_map.get(track_id)
        if track.final_baler is None:
            self._on_baler_finalized(track)
        
        self.crops.pop(track_id, None)
        self.log_info(f"Track crops removed: {track_id}")