# src/rubber_tracker/track/services/classify/classify_service.py
import time
import threading
from queue import Queue, Full, Empty
from typing import Optional, Callable, Any, List, Tuple

import numpy as np
from ultralytics import YOLO

from .buffer import ClassificationBuffer
from rubber_tracker.utils import ModuleLogger, CustomThread

class BatchClassifyService(ModuleLogger):
    """
    Batch-capable classification service.

    - process_batch(crops, track_ids, callback) enqueues a batch.
    - worker thread consumes batches in FIFO order and performs batch inference.
    - callback signature: callback(track_ids, results)
    """
    def __init__(self, model_path: str, class_names: list, imgsz: int, buffer_size: int = 300):
        super().__init__(self.__class__.__name__)
        self.model_path = model_path
        self.class_names = class_names
        self.imgsz = imgsz

        # init model
        self.model = YOLO(self.model_path)
        self._warmup()

        # buffer and worker
        self.buffer = ClassificationBuffer(max_size=buffer_size)
        self.buffer_logging_interval = 3
        self.last_log_time = time.time()
        self._stop_event = threading.Event()
        self.worker = CustomThread(
            name=self.__class__.__name__ + "_worker",
            task=self._worker,
            interval=0.001,
            loop=True
        )
        self.worker.start()
        self.log_info("BatchClassifyService started (batch).")

    # -------------------
    # Public API
    # -------------------
    def process_batch(self, track_id: int, crops: List[np.ndarray], callback: Optional[Callable[[List[int], List[Any]], None]] = None) -> bool:
        """
        Enqueue a batch for classification. Non-blocking.
        callback(track_id, results) will be called from worker thread when done.
        """
        return self.buffer.put(track_id, crops, callback)

    def qsize(self) -> int:
        return self.buffer.qsize()

    def stop(self):
        try:
            self.worker.stop()
            self.log_info("BatchClassifyService worker stopped.")
        except Exception:
            pass

    # -------------------
    # Internal
    # -------------------
    def _worker(self):
        if time.time() - self.last_log_time >= self.buffer_logging_interval:
            self.log_info(f"Classification buffer size: {self.buffer.qsize()}")
            self.last_log_time = time.time()
        
        item = self.buffer.get(timeout=0.02)
        if item is None:
            return

        track_id, crops, callback = item
        try:
            t0 = time.time()
            results = self._infer_batch(crops)
            t1 = time.time()
            self.log_info(f"Batch inference time: {(t1 - t0):.2f} seconds")
        except Exception as e:
            self.log_error(f"Batch inference error for track {track_id}: {e}")
            results = None

        # Always call callback (if provided). Callback must be resilient.
        if callback:
            try:
                callback(track_id, results)
            except Exception as e:
                # Callback errors shouldn't crash worker
                self.log_error(f"Batch callback error for track {track_id}: {e}")

    def _infer_batch(self, imgs: List[np.ndarray]) -> Tuple[List[int], List[float]]:
        """
        Run model inference on a list of images and return top1 predictions aligned with imgs list.
        """
        # ultralytics accepts list input; returns list of results aligned to inputs
        out = self.model(imgs, imgsz=self.imgsz, verbose=False)
        # out is list-like; each item has .probs.top1 if model provides probs
        cls_ids = []
        confs = []
        for o in out:
            try:
                cls_ids.append(o.probs.top1)
                confs.append(o.probs.top1conf)
            except Exception as e:
                self.log_error(f"Batch inference error: {e}")
                cls_ids.append(None)
                confs.append(None)
        return cls_ids, confs

    def _warmup(self):
        try:
            for _ in range(3):
                dummy = np.random.randint(0, 255, (self.imgsz, self.imgsz, 3), dtype=np.uint8)
                self.model(dummy, imgsz=self.imgsz, verbose=False)
        except Exception:
            # ignore warmup failures here, model may still work
            pass
