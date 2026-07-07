import os
import re
import threading
from datetime import datetime
from typing import Any, Dict, Optional

import cv2

from rubber_tracker.utils import CustomThread, ProcessLogger, load_config

from .frame_store import FrameStore

_SAFE = re.compile(r"[^A-Za-z0-9_.-]")


def _safe(value: Any, limit: int = 60) -> str:
    text = _SAFE.sub("_", str(value) if value is not None else "none")
    return (text[:limit] or "empty")


class EventImageSaver(ProcessLogger):
    def __init__(self, frame_store: FrameStore, config: Optional[Dict[str, Any]] = None):
        super().__init__(self.__class__.__name__)
        if frame_store is None:
            raise ValueError("frame_store must not be None")

        cfg = self._load_config(config)
        self._frames = frame_store
        self._enabled = bool(cfg["enabled"])
        self._save_dir = str(cfg["save_dir"])
        self._draw_bbox = bool(cfg["draw_bbox"])
        self._draw_all_tracks = bool(cfg["draw_all_tracks"])
        self._by_event_type = bool(cfg["organize_by_event_type"])
        self._jpeg_quality = max(1, min(100, int(cfg["jpeg_quality"])))
        self._pre = max(0, int(cfg["pre_event_frames"]))
        self._post = max(0, int(cfg["post_event_frames"]))
        self._buffer_size = max(1, int(cfg["frame_buffer_size"]))
        self._max_pending = max(1, int(cfg["max_pending_events"]))
        self._max_daily = max(0, int(cfg["max_events_per_day"]))
        if self._buffer_size < self._pre + self._post + 1:
            raise ValueError("frame_buffer_size must be >= pre_event_frames + post_event_frames + 1")

        self._frames.set_buffer_size(self._buffer_size)
        self._filters = self._parse_filters(cfg["enabled_event_prefixes"])
        self._pending = []
        self._pending_lock = threading.Lock()
        self._daily_counts: Dict[str, int] = {}
        self._worker: Optional[CustomThread] = None
        self._stop_flag = threading.Event()
        self._drops_count = 0
        self._saved_count = 0

    def start(self) -> None:
        if not self._enabled:
            self.log_info("EventImageSaver disabled")
            return
        try:
            os.makedirs(self._save_dir, exist_ok=True)
        except Exception as e:
            self.log_error(f"Cannot create save_dir '{self._save_dir}': {e}")
            self._enabled = False
            return
        if self._worker is not None:
            return
        self._worker = CustomThread(
            name=self.__class__.__name__ + "_worker",
            task=self._worker_task,
            interval=0,
        )
        self._worker.start()
        self.log_info(
            f"EventImageSaver started | save_dir={self._save_dir} | "
            f"frames={self._pre}+{self._post} | buffer={self._buffer_size} | max_daily={self._max_daily}"
        )

    def stop(self) -> None:
        self._stop_flag.set()
        if self._worker is not None:
            try:
                self._worker.stop()
            except Exception as e:
                self.log_warning(f"stop error: {e}")
            self._worker = None
        self.log_info(f"EventImageSaver stopped | saved={self._saved_count} | drops={self._drops_count}")

    def on_event(self, evt: Optional[dict]) -> None:
        try:
            self._handle(evt)
        except Exception as e:
            self.log_error(f"on_event unhandled: {e}")

    def _handle(self, evt: Optional[dict]) -> None:
        if not self._enabled or not isinstance(evt, dict):
            return

        event_type = evt.get("event") or evt.get("type")
        if not isinstance(event_type, str) or not self._is_enabled(event_type, evt.get("id", "")):
            return

        seq = self._frames.current_seq()
        if seq <= 0:
            return

        now = datetime.now()
        date_key = now.strftime("%Y-%m-%d")
        if self._max_daily and self._daily_counts.get(date_key, 0) >= self._max_daily:
            self._drop(f"daily limit reached: {date_key}")
            return

        with self._pending_lock:
            if len(self._pending) >= self._max_pending:
                self._drop("pending queue full")
                return
            self._pending.append({
                "evt": dict(evt),
                "event_seq": seq,
                "start_seq": max(1, seq - self._pre),
                "end_seq": seq + self._post,
                "created_at": now,
            })
            self._daily_counts[date_key] = self._daily_counts.get(date_key, 0) + 1

    def _worker_task(self) -> None:
        if self._stop_flag.is_set():
            return
        item = self._pop_ready()
        if item is None:
            return
        try:
            self._save_one(item)
            self._saved_count += 1
        except Exception as e:
            self.log_error(f"save_one error: {e}")

    def _pop_ready(self) -> Optional[dict]:
        current = self._frames.current_seq()
        with self._pending_lock:
            for idx, item in enumerate(self._pending):
                if current >= item["end_seq"]:
                    self._pending.pop(idx)
                    break
            else:
                return None

        frames = self._frames.frames_between(item["start_seq"], item["end_seq"])
        return {**item, "frames": frames} if frames else None

    def _save_one(self, item: dict) -> None:
        evt = item["evt"]
        frames = item.get("frames") or []
        if not frames:
            return

        out_dir = self._event_dir(item, evt)
        os.makedirs(out_dir, exist_ok=True)

        for frame in frames:
            seq = frame["seq"]
            path = os.path.join(out_dir, self._frame_filename(seq, item["event_seq"]))
            self._write_label(path, frame["frame"].shape, frame["tracks"])
            img = self._prepare_image(frame["frame"], frame["tracks"], evt)
            if not cv2.imwrite(path, img, [int(cv2.IMWRITE_JPEG_QUALITY), self._jpeg_quality]):
                self.log_error(f"cv2.imwrite returned False: {path}")

    def _frame_filename(self, seq: int, event_seq: int) -> str:
        if seq == event_seq:
            return f"{seq:08d}_event.jpg"
        if seq < event_seq:
            return f"{seq:08d}_pre_{event_seq - seq:03d}.jpg"
        return f"{seq:08d}_post_{seq - event_seq:03d}.jpg"

    def _event_dir(self, item: dict, evt: dict) -> str:
        event_type = str(evt.get("event") or evt.get("type") or "unknown")
        created = item["created_at"]
        stamp = created.strftime("%Y%m%d_%H%M%S") + f"_{created.microsecond // 1000:03d}"
        parts = [stamp, _safe(event_type), _safe(evt.get("id", "unknown"))]
        if evt.get("rejected"):
            parts.append("REJECTED")

        path = os.path.join(self._save_dir, created.strftime("%Y-%m-%d"))
        if self._by_event_type:
            tokens = event_type.split("_")
            path = os.path.join(path, _safe("_".join(tokens[:2]) if len(tokens) >= 2 else event_type))
        return os.path.join(path, "_".join(parts))

    def _prepare_image(self, frame, tracks: Dict[int, Dict[str, Any]], evt: dict):
        if not self._draw_bbox:
            return frame
        if self._draw_all_tracks:
            for tid, info in tracks.items():
                self._draw_box(frame, info.get("bbox"), label=f"#{tid}")
        self._draw_label(frame, evt)
        return frame

    def _draw_box(self, img, bbox, color=(150, 150, 150), label="") -> None:
        if not bbox or len(bbox) < 4:
            return
        try:
            h, w = img.shape[:2]
            x1, y1, x2, y2 = [int(v) for v in bbox[:4]]
            x1, x2 = max(0, min(w - 1, x1)), max(0, min(w - 1, x2))
            y1, y2 = max(0, min(h - 1, y1)), max(0, min(h - 1, y2))
            cv2.rectangle(img, (x1, y1), (x2, y2), color, 1)
            if label:
                cv2.putText(img, label, (x1 + 2, max(12, y1 - 3)), cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1, cv2.LINE_AA)
        except Exception:
            pass

    def _draw_label(self, img, evt: dict) -> None:
        event_type = str(evt.get("event") or evt.get("type") or "")
        parts = [event_type, f"id={evt.get('id', '')}", f"zone={evt.get('zone') or ''}"]
        if evt.get("baler") is not None:
            parts.append(f"baler={evt['baler']}")
        if evt.get("final_baler") is not None:
            parts.append(f"final={evt['final_baler']}")
        if evt.get("rejected"):
            parts.append("REJECTED")

        label = " | ".join(parts)
        font = cv2.FONT_HERSHEY_SIMPLEX
        (tw, th), bl = cv2.getTextSize(label, font, 0.5, 1)
        color = (0, 0, 180) if evt.get("rejected") else (0, 160, 0)
        cv2.rectangle(img, (4, 4), (min(img.shape[1] - 1, tw + 12), th + bl + 12), color, -1)
        cv2.putText(img, label, (8, th + 8), font, 0.5, (255, 255, 255), 1, cv2.LINE_AA)

    def _write_label(self, image_path: str, shape, tracks: Dict[int, Dict[str, Any]]) -> None:
        h, w = shape[:2]
        lines = [line for info in tracks.values() if (line := self._yolo_line(info.get("bbox"), w, h))]
        with open(os.path.splitext(image_path)[0] + ".txt", "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))

    def _yolo_line(self, bbox, w: int, h: int) -> Optional[str]:
        if not bbox or len(bbox) < 4 or w <= 0 or h <= 0:
            return None
        x1, y1, x2, y2 = [float(v) for v in bbox[:4]]
        x1, x2 = sorted((max(0.0, min(w, x1)), max(0.0, min(w, x2))))
        y1, y2 = sorted((max(0.0, min(h, y1)), max(0.0, min(h, y2))))
        if x2 <= x1 or y2 <= y1:
            return None
        vals = [((x1 + x2) / 2) / w, ((y1 + y2) / 2) / h, (x2 - x1) / w, (y2 - y1) / h]
        return "0 " + " ".join(f"{v:.6f}" for v in vals)

    def _is_enabled(self, event_type: str, ext_id: Any) -> bool:
        if self._filters is None:
            return True
        ext_id = str(ext_id)
        for prefix, id_prefixes in self._filters.items():
            if event_type.startswith(prefix):
                return not id_prefixes or any(ext_id.startswith(p) for p in id_prefixes)
        return False

    def _drop(self, reason: str) -> None:
        self._drops_count += 1
        if self._drops_count % 100 == 1:
            self.log_warning(f"Event image dropped: {reason}, drops={self._drops_count}")

    def _load_config(self, config: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if config is not None:
            return dict(config)
        return load_config()["event_image_saver"]

    @staticmethod
    def _parse_filters(filters: Any) -> Optional[Dict[str, list[str]]]:
        if filters is None:
            return None
        if isinstance(filters, (list, tuple)):
            return {str(prefix): [] for prefix in filters}
        if not isinstance(filters, dict):
            raise TypeError("enabled_event_prefixes must be dict, list, or null")
        return {
            str(prefix): [] if ids is None else [str(x) for x in ids]
            for prefix, ids in filters.items()
        }
