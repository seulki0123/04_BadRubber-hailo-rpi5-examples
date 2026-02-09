import time

import cv2
import numpy as np

def open_camera(label, url, log_info, log_warning, log_error, target_fps=None, target_w=None, target_h=None):
    cap = cv2.VideoCapture(url)
    if not cap.isOpened():
        log_error(f"Failed to open {label}: {url}")
        raise ConnectionError(f"IP Camera open failed: {url}")

    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = int(cap.get(cv2.CAP_PROP_FPS))

    log_info(f"{label} {url} → {w}x{h}@{fps}fps")

    if target_fps and fps != target_fps:
        log_warning(f"FPS mismatch between {label} and config: {fps} != {target_fps}")
    if target_w and target_h and (w != target_w or h != target_h):
        log_warning(f"Size mismatch between {label} and config: {w}x{h} != {target_w}x{target_h} (resize will be applied)") 

    return cap, w, h, fps

def resize_if_needed(frame, target_w, target_h):
    h, w = frame.shape[:2]
    if w != target_w or h != target_h:
        frame = cv2.resize(frame, (target_w, target_h))
    return frame

def safe_read(cap, fps, log_error, label):
    ret, frame = cap.read()
    if not ret or frame is None:
        log_error(f"{label}: Failed to read frame")
        time.sleep(1 / fps)
        return None
    return frame

def combine_frames_vertical(frame1, frame2, blank=0):
    if blank > 0:
        # frame1, frame2와 같은 width, channel을 가진 검은 공백
        h_blank = np.zeros((blank, frame1.shape[1], frame1.shape[2]), dtype=frame1.dtype)
        return cv2.vconcat([frame1, h_blank, frame2])
    else:
        return cv2.vconcat([frame1, frame2])


def combine_frames_horizontal(frame1, frame2, blank=0):
    if blank > 0:
        # frame1, frame2와 같은 height, channel을 가진 검은 공백
        w_blank = np.zeros((frame1.shape[0], blank, frame1.shape[2]), dtype=frame1.dtype)
        return cv2.hconcat([frame1, w_blank, frame2])
    else:
        return cv2.hconcat([frame1, frame2])


def blank_frame(w, h):
    return np.zeros((h, w, 3), dtype="uint8")