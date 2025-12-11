# src/rubber_tracker/track/services/state/baler_service.py
import threading
from typing import Dict, Any, Optional, List, Tuple

from rubber_tracker.utils import ModuleLogger
from ...domain.track_state import TrackState


class BalerService(ModuleLogger):
    """
    Batch-oriented BalerService.

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
        self.track_map = track_map

        # concurrency
        self._lock = threading.Lock()

        # tracks that were deleted/expired and should ignore callbacks
        self.deleted_tracks = set()

        # inflight classification count per track
        self._inflight: Dict[int, int] = {}

        # batch buffer (list of tuples (track_id, crop))
        self._batch_lock = threading.Lock()
        self._batch_crops: List[Tuple[int, Any]] = []

    # ----------------------------------------------------------------------
    def update(self, track: TrackState, bbox, frame, zone: Optional[str]):
        """
        Called per-frame per-track. Collect crops into local batch instead of sending immediately.
        """
        actions = []
        track.update_position(bbox)

        # -----------------------
        # 1) collect crop for classification (batch)
        # -----------------------
        if zone and self._ready(track):
            crop = self.capture_service.crop(
                bbox,
                frame,
                save_folder=f"{zone}_{track.track_id:06d}",
                save_infos=[track.speed],
            )
            if crop is not None:
                with self._batch_lock:
                    self._batch_crops.append((track.track_id, crop))

                # mark inflight increment will happen on flush_batch (atomic increment there)
                track.set_text_color((0, 255, 0))
            else:
                # couldn't crop -> visual feedback
                track.set_text_color((255, 0, 0))

        # -----------------------
        # 2) finalization check (unchanged logic)
        # -----------------------
        if self._should_finalize(track):
            self.log_info(
                f"[FINALIZE] track={track.track_id}, votes={track.baler_votes}, "
                f"inflight={self._inflight.get(track.track_id, 0)}, "
                f"speed={track.speed:.2f}"
            )

            track.update_final_baler()
            track.set_text_color(None)

            with self._lock:
                self._inflight.pop(track.track_id, None)

            actions.append({
                "event_type": "final_baler",
                "zone": zone,
                "delay": 0,
            })

        return actions

    # ----------------------------------------------------------------------
    def flush_batch(self):
        """
        Send collected crops as a single batch to classify_service.
        Should be called periodically (e.g., once per frame after updates).
        """
        with self._batch_lock:
            if not self._batch_crops:
                return

            # separate ids and crops
            entries = self._batch_crops
            self._batch_crops = []

        track_ids = [t for (t, _) in entries]
        crops = [c for (_, c) in entries]

        # Try to enqueue batch. If buffer full, classify_service.process_batch returns False.
        enqueued = self.classify_service.process_batch(
            crops=crops,
            track_ids=track_ids,
            callback=self._on_batch_result,
        )

        if enqueued:
            with self._lock:
                for tid in track_ids:
                    self._inflight[tid] = self._inflight.get(tid, 0) + 1

            self.log_debug(f"[FLUSH] sent batch size={len(track_ids)} inflight snapshot={self._inflight}")
        else:
            # buffer full -> drop entire batch (could be improved to partial enqueue)
            self.log_warning(f"[FLUSH-DROP] batch size={len(track_ids)} dropped (buffer full)")
            # provide visual feedback: set text color red for dropped tracks
            for tid in track_ids:
                track = self.track_map.get(tid)
                if track:
                    track.set_text_color((255, 0, 0))

    # ----------------------------------------------------------------------
    # Callback from classify_service (batch)
    # ----------------------------------------------------------------------
    def _on_batch_result(self, track_ids: List[int], results: List[Any]):
        """
        Called by classify_service.worker thread when batch inference completes.

        - track_ids: list of track ids in same order as results
        - results: list of classification results (None allowed)
        """
        if not track_ids:
            return

        # adjust inflight counts atomically
        with self._lock:
            for tid in track_ids:
                cnt = self._inflight.get(tid, 0)
                if cnt <= 1:
                    self._inflight.pop(tid, None)
                else:
                    self._inflight[tid] = cnt - 1

        # apply results (thread-safe on TrackState via add_vote)
        for tid, res in zip(track_ids, results):
            # ignore deleted tracks
            if tid in self.deleted_tracks:
                self.log_debug(f"[CALLBACK-IGNORED] deleted track={tid}")
                continue

            track = self.track_map.get(tid)
            if track is None:
                self.log_debug(f"[CALLBACK-IGNORED] missing track={tid}")
                continue

            if res is not None:
                track.add_vote(res)
                self.log_debug(f"[VOTE] track={tid}, class={res}, votes={track.baler_votes}")

    # ----------------------------------------------------------------------
    # Mark track deleted (optional utility)
    # ----------------------------------------------------------------------
    def mark_deleted(self, track_id: int):
        with self._lock:
            self.deleted_tracks.add(track_id)
            self._inflight.pop(track_id, None)

    # ----------------------------------------------------------------------
    # Ready Logic (unchanged)
    # ----------------------------------------------------------------------
    def _ready(self, track: TrackState) -> bool:
        if track.final_baler is not None:
            return False

        if not self.speed_service.is_slow(track.speed):
            return False

        votes = sum(track.baler_votes.values())
        ok = votes < self.cls_limit

        self.log_debug(
            f"[_ready] track={track.track_id}, votes={votes}, limit={self.cls_limit}, "
            f"speed={track.speed:.2f}, slow={self.speed_service.is_slow(track.speed)}, -> {ok}"
        )
        return ok

    # ----------------------------------------------------------------------
    # Finalize Logic (unchanged)
    # ----------------------------------------------------------------------
    def _should_finalize(self, track: TrackState) -> bool:
        if not track.speed_computed:
            return False

        if track.final_baler is not None:
            return False

        votes = sum(track.baler_votes.values())
        fully_stopped = self.speed_service.is_stop(track.speed)

        with self._lock:
            inflight = self._inflight.get(track.track_id, 0)

        decision = (votes >= self.cls_limit or fully_stopped) and inflight == 0

        self.log_debug(
            f"[_should_finalize] track={track.track_id}, votes={votes}, limit={self.cls_limit}, "
            f"stopped={fully_stopped}, inflight={inflight}, -> {decision}"
        )

        return decision