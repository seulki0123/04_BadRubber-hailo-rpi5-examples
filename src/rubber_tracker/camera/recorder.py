import atexit
import os
import signal
import time
from datetime import datetime

import cv2

from rubber_tracker.utils import ProcessLogger, load_config

class Recorder(ProcessLogger):
    def __init__(self):
        super().__init__(__class__.__name__)
        config = load_config()
        save_root, record, save_frames, draw, max_record_seconds = self._get_save_config()
        self.draw = draw
        self.record = record
        self.save_root = save_root
        self.save_frames = save_frames
        self.max_record_seconds = max_record_seconds
        self.vid_path, self.frame_dir = self._save_dir()

        self.fps = config["ipcamera"]["fps"]

        self.writer = None
        self.is_recording = True

        self.frame_count = 0

        self.update_interval = config["recorder"]["update_interval"]
        self.last_update_time = time.time()

        # ─── 자동 종료 (max_record_seconds) 상태 ───────────────────────────────
        # max_record_seconds 가 양수일 때, record / save_frames 가 활성화된 시점부터
        # 그 시간(초) 이 지나면 record / save_frames 를 자동으로 False 로 강제한다.
        # config 자체는 사용자가 켜둔 그대로이므로, 한 번 자동 종료된 세션은
        # config 를 토글하지 않는 한 다시 시작되지 않게 sticky 플래그로 보호.
        self._auto_stopped = False
        self._auto_stopped_signature = None
        # 녹화 세션이 활성화된 시각. 비활성 / 자동 종료 직후엔 None.
        self._record_start_time = (
            time.time() if (self.record or self.save_frames) else None
        )

        # mp4 moov atom은 VideoWriter.release() 호출 시에만 기록되므로,
        # 예상치 못한 종료 경로에서도 join()이 불려 writer가 닫히도록 보장한다.
        atexit.register(self._finalize_on_exit)
        try:
            signal.signal(signal.SIGTERM, self._signal_handler)
        except (ValueError, OSError):
            # 메인 스레드 밖에서 인스턴스화된 경우 signal 등록 불가 — atexit만으로도 OK
            pass

    def _finalize_on_exit(self):
        try:
            self.join()
        except Exception:
            pass

    def _signal_handler(self, signum, frame):
        try:
            self.join()
        except Exception:
            pass
        signal.signal(signum, signal.SIG_DFL)
        os.kill(os.getpid(), signum)

    def _start(self, w, h):
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        self.writer = cv2.VideoWriter(self.vid_path, fourcc, self.fps, (w, h))
        self.log_info(f"Started recording to {self.vid_path}")

    def write_frame(self, frame, bboxes):
        self.frame_count += 1

        if time.time() - self.last_update_time > self.update_interval:
            self.last_update_time = time.time()
            if self._update_state():
                return
            # config 변경이 없어도 max_record_seconds 도달 시 자동 종료(-> config 자동으로 False로 수정하지 않음.)
            if self._check_max_record_time():
                return

        if not self.record:
            return

        if not self.is_recording:
            return

        if self.writer is None:
            h, w = frame.shape[:2]
            self._start(w, h)

        if self.writer is not None:
            self.writer.write(frame)
        
        if self.save_frames:
            self._save_frame(frame, bboxes)

    def join(self):
        if self.writer is not None:
            self.writer.release()
            self.writer = None
            self.log_info("Stopped recording.")
        self.is_recording = False

    def _save_dir(self):
        config = load_config()

        # ipcamera.urls 표준 키 사용 (load_config 가 url/url1/url2 도 합성해서 채움).
        urls = list(config["ipcamera"].get("urls", []) or [])
        if not urls:
            urls = ["null"]
        filenames = [os.path.basename(u) if u else "null" for u in urls]
        # cam2 가 없는 단일 카메라 케이스도 기존 파일명 패턴 유지
        if len(filenames) < 2:
            filenames.append("null")
        video_name = f"{'_'.join(filenames[:2])}.mp4"

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        save_dir = os.path.join(self.save_root, f"{timestamp}_{video_name}")

        vid_path = os.path.join(save_dir, video_name)
        frame_dir = os.path.join(save_dir, "frames")

        os.makedirs(frame_dir, exist_ok=True)

        self.log_info(f"Save directory created: {save_dir}")

        return vid_path, frame_dir

    def _save_frame(self, frame, bboxes):
        filename = f"frame_{self.frame_count:06d}.jpg"
        filepath = os.path.join(self.frame_dir, filename)
        cv2.imwrite(filepath, frame)
        with open(filepath.replace(".jpg", ".txt"), "w") as f:
            for bbox in bboxes:
                f.write(f"{' '.join(map(str, bbox))}\n") # xywhn

    def _get_save_config(self):
        config = load_config()
        rcfg = config["recorder"]
        save_root = rcfg["save_root"]
        record = rcfg["record"]
        save_frames = rcfg["save_frames"]
        draw = rcfg["draw"]
        # max_record_seconds: None / 0 / 음수 / 잘못된 값 = 비활성화 (기존 동작 유지)
        raw = rcfg.get("max_record_seconds")
        try:
            max_seconds = int(raw) if raw is not None else 0
        except (TypeError, ValueError):
            max_seconds = 0
        if max_seconds < 0:
            max_seconds = 0
        return save_root, record, save_frames, draw, max_seconds

    def _get_draw_state(self):
        return self.draw
        
    def _update_state(self):
        save_root, record, save_frames, draw, max_record_seconds = self._get_save_config()

        # 자동 종료 sticky 처리:
        # 한 번 max_record_seconds 로 종료된 세션은, 사용자가 config 의
        # (record, save_frames) 를 종료 시점과 다르게 바꾸기 전까지 "변경 없음"
        # 으로 간주한다. 그렇지 않으면 config(True) ↔ self(False) 차이를 매번
        # 새 변경으로 보고 무한히 재시작된다.
        if self._auto_stopped:
            if (record, save_frames) == self._auto_stopped_signature:
                # max_record_seconds 만 hot-update 허용 (다음 세션에 반영)
                self.max_record_seconds = max_record_seconds
                return False
            # config 가 토글됨 → sticky 해제하고 정상 흐름 진행
            self.log_info("Auto-stopped sticky cleared (config toggled)")
            self._auto_stopped = False
            self._auto_stopped_signature = None

        if save_root != self.save_root \
            or record != self.record \
            or save_frames != self.save_frames \
            or draw != self.draw:

            # init
            self.join()
            self.is_recording = True

            # update
            self.draw = draw
            self.record = record
            self.save_root = save_root
            self.save_frames = save_frames
            self.max_record_seconds = max_record_seconds
            self.vid_path, self.frame_dir = self._save_dir()

            # 녹화/프레임 저장 활성화 시점 기록 (자동 종료 카운트의 기준)
            self._record_start_time = (
                time.time() if (record or save_frames) else None
            )

            self.log_info(f"Recorder state updated")

            return True

        # config 변경이 없을 때도 max_record_seconds 만은 hot-update 허용
        self.max_record_seconds = max_record_seconds
        return False

    # ------------------------------------------------------------
    # 자동 종료 (max_record_seconds)
    # ------------------------------------------------------------
    def _check_max_record_time(self):
        """녹화 시작 시점부터 max_record_seconds 가 지났으면 자동 종료.

        Returns: True 면 이번 사이클에서 자동 종료가 발동되어 후속 처리를
        하지 말아야 함을 의미.
        """
        if self.max_record_seconds <= 0:
            return False
        if not (self.record or self.save_frames):
            return False
        if self._record_start_time is None:
            return False

        elapsed = time.time() - self._record_start_time
        if elapsed < self.max_record_seconds:
            return False

        self._auto_stop(elapsed)
        return True

    def _auto_stop(self, elapsed):
        """max_record_seconds 도달 → 녹화 중단 + sticky flag 세팅."""
        self.log_info(
            f"[auto-stop] reached max_record_seconds={self.max_record_seconds}s "
            f"(elapsed={elapsed:.1f}s, record={self.record}, save_frames={self.save_frames}). "
            "Toggle recorder.record/save_frames in config to start a new session."
        )
        # join() 이 writer 닫고 self.is_recording = False 세팅
        self.join()
        self._auto_stopped = True
        self._auto_stopped_signature = (self.record, self.save_frames)
        self.record = False
        self.save_frames = False
        self._record_start_time = None