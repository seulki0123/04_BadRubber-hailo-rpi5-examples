from typing import Literal

import numpy as np
import cv2

from interfaces.video import VideoSource

MergeMode = Literal["vertical", "horizontal"]

def check_video_infos(video_sources: list[VideoSource]) -> None:
    if not video_sources:
        raise ValueError("video_sources is empty")

    w, h = video_sources[0].width, video_sources[0].height
    fps = video_sources[0].fps
    video_format = video_sources[0].format

    if not all(s.width == w and s.height == h and s.fps == fps and s.format == video_format for s in video_sources):
        raise ValueError("All video sources must have the same size, fps, and format")

def get_video_size(video_sources: list[VideoSource], merge_mode: MergeMode) -> tuple[int, int]:
    check_video_infos(video_sources)

    if merge_mode == "vertical":
        return video_sources[0].width, sum(source.height for source in video_sources)
    elif merge_mode == "horizontal":
        return sum(source.width for source in video_sources), video_sources[0].height
    else:
        raise ValueError(f"Invalid merge mode: {merge_mode}")

def get_video_infos(video_sources: list[VideoSource]) -> dict[str, int | float | str]:
    check_video_infos(video_sources)

    return {
        "width": video_sources[0].width,
        "height": video_sources[0].height,
        "fps": video_sources[0].fps,
        "format": video_sources[0].format,
    }

def merge_frames(frames: list[np.ndarray], merge_mode: MergeMode) -> np.ndarray:
    if merge_mode == "vertical":
        return cv2.vconcat(frames)
    elif merge_mode == "horizontal":
        return cv2.hconcat(frames)
    else:
        raise ValueError(f"Invalid merge mode: {merge_mode}")