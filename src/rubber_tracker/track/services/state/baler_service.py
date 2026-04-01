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
        self.baler_cls_results = {
            # track_id: {
            #   "speeds": [],
            #   "cls_ids": [],
            #   "confs": [],
            #   "finalized": False
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
            buffer_added = self.classify_service.process_batch(
                track.track_id,
                [crop],
                self._on_classification_result
            )
            self.log_info(f"● Buffer added: {buffer_added} for track {track.track_id}")

        # send classification request
        if self._should_finalize(track):
            result = self.baler_cls_results.get(track.track_id)
            if not result or not result["cls_ids"]:
                baler = self.classify_fallback_baler
            else:
                cls_ids = np.array(result["cls_ids"][:])
                confs = np.array(result["confs"][:])
                pairs = [(int(cid), round(float(cf), 2)) for cid, cf in zip(cls_ids, confs)]
                self.log_info(f"Classification raw: {pairs}")

                filtered = cls_ids[confs >= self.cls_conf_threshold]
                filtered = filtered[-3:]

                if len(filtered) == 0:
                    baler = self.classify_fallback_baler
                else:
                    values, counts = np.unique(filtered, return_counts=True)
                    baler = int(values[np.argmax(counts)])

            track.finalize_baler(baler)
            self._on_baler_finalized(track)

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
            return
            
        self.log_info(f"●● Classification result: {cls_ids}, {confs}")
        if track_id not in self.baler_cls_results:
            self.baler_cls_results[track_id] = self._build_result_state(finalized=False)
        self.baler_cls_results[track_id]["cls_ids"].extend(cls_ids)
        self.baler_cls_results[track_id]["confs"].extend(confs)

    # conditions
    def _ready(self, track: TrackState) -> bool:
        if track.final_baler is not None:
            return False

        result = self.baler_cls_results.get(track.track_id)
        current_len = len(result["cls_ids"]) if result else 0

        if not self.speed_service.is_slow(track.speed):
            self.log_info(f"Track {track.track_id} is not slow ({track.speed:.2f} pixels per second), skipping classification")
            return False
        
        if current_len >= self.cls_limit:
            self.log_info(f"Track {track.track_id} has reached the classification limit, skipping classification")
            return False

        return True

    def _should_finalize(self, track: TrackState) -> bool:
        result = self.baler_cls_results.get(track.track_id)
        if not result:
            return False

        return (
            track.final_baler is None
            and not result["finalized"]
            and (
                self.speed_service.is_stop(track.speed)
                or len(result.get("cls_ids", [])) >= self.cls_limit
            )
        )

    def _on_baler_finalized(self, track: TrackState, event_type="final_baler"):
        result = self.baler_cls_results.get(track.track_id)
        if result is None:
            self.baler_cls_results[track.track_id] = self._build_result_state(finalized=True)
        else:
            result["finalized"] = True
        if self.on_baler_finalized:
            self.on_baler_finalized(track, event_type=event_type)

    def on_track_removed(self, track_id: int):
        track = self.track_map.get(track_id)
        if track.final_baler is None:
            self._on_baler_finalized(track)
        
        self.baler_cls_results.pop(track_id, None)
        self.log_info(f"Track baler classification results removed: {track_id}")

    def _build_result_state(self, finalized: bool = False):
        return {
            "cls_ids": [],
            "confs": [],
            "finalized": finalized
        }