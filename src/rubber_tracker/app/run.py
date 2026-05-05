from rubber_tracker.camera import IPCamera, Recorder
from rubber_tracker.detect import DetectionApp
from rubber_tracker.network import NetworkEventHub
from rubber_tracker.track import TrackManager, TrackEventHandler, TrackDispatcher
from rubber_tracker.monitoring import Monitoring
from rubber_tracker.sync import SyncManager
from rubber_tracker.utils import Drawer, load_config
# 이벤트 이미지 저장 기능 (기본 disabled, config.event_image_saver.enabled 로 활성화)
from rubber_tracker.event_image_saver import FrameStore, ImageEventCapture, EventImageSaver
from rubber_tracker.fileclenaer import FileCleanerService


def _build_per_profile(
    profile_id,
    masksize,
    *,
    image_saver,
    recorder,
    stream_status_getter,
):
    """단일 프로파일에 속하는 인스턴스 (TrackManager / SyncManager / NetworkEventHub
    / Drawer) 를 만들고 콜백을 배선한 뒤 (track_manager, drawer, net) 를 반환한다.
    """
    track_manager = TrackManager(masksize, profile_id=profile_id)
    sync_manager = SyncManager(profile_id=profile_id)
    net = NetworkEventHub(profile_id=profile_id)
    track_manager.event_service.set_notifier_send(net.send_track_event_count)

    drawer = Drawer(
        stream_status_getter=stream_status_getter,
        tracks_info_getter=track_manager.get_tracks_info,
        masks_getter=track_manager.get_masks,
        message_getter=track_manager.get_messages,
        recorder=recorder,
    )

    track_manager.add_callback(net.notify_flow)
    track_manager.add_callback(image_saver.on_event)
    net.add_listener_callback(track_manager.add_external_id)
    net.add_listener_callback(sync_manager.handle_pause)

    track_manager.add_callback(sync_manager.add_external_time)
    track_manager.add_callback(sync_manager.add_internal_time)
    track_manager.add_callback(sync_manager.add_external_baler)
    track_manager.add_callback(sync_manager.add_internal_baler)
    sync_manager.add_callback(track_manager.on_sync)

    return track_manager, drawer, net


def run():
    # ----- 공용 인스턴스 -----
    cam = IPCamera()
    width, height, video_sink = cam.get_stream_settings()
    layout = cam.get_layout()

    app = DetectionApp()
    rsrc = Monitoring()
    file_cleaner = FileCleanerService()

    # 합성 프레임 1장을 기록 / 캐싱하므로 Recorder / FrameStore / ImageSaver 는 공용.
    recorder = Recorder()
    frame_store = FrameStore()
    image_saver = EventImageSaver(frame_store)

    # ----- 프로파일 목록 -----
    config = load_config()
    profile_ids = config["_profile_ids"]

    # ----- 프로파일별 인스턴스 -----
    track_managers = []
    drawers = []
    nets = []
    for pid in profile_ids:
        tm, dr, net = _build_per_profile(
            pid,
            masksize=(width, height),
            image_saver=image_saver,
            recorder=recorder,
            stream_status_getter=cam.get_stream_status,
        )
        track_managers.append(tm)
        drawers.append(dr)
        nets.append(net)

    # ----- Track 라우팅 (dispatcher) -----
    dispatcher = TrackDispatcher(
        managers=track_managers,
        cam_h=layout["cam_h"],
        blank=layout["blank"],
    )

    # 이벤트 이미지 캡처는 dispatcher 위에 한 번만 감싼다 (frame_store 공용).
    event_handler = ImageEventCapture(dispatcher, frame_store)

    # 그리기 콜백 — 멀티 프로파일이면 모든 drawer 를 순차 호출한다.
    if len(drawers) == 1:
        draw_callback = drawers[0].draw
    else:
        def draw_callback(*args, **kwargs):
            for dr in drawers:
                dr.draw(*args, **kwargs)

    # ----- GStreamer / Hailo 파이프라인 (공용) -----
    app.create_pipeline(width, height, video_sink, event_handler, draw_callback)
    cam.set_appsrc(app.get_gst_pipeline())

    # ----- 기동 -----
    rsrc.run()
    file_cleaner.run()
    for net in nets:
        net.run()
    cam.run()
    image_saver.start()  # 워커 스레드 기동 (disabled면 no-op)
    app.run()


if __name__ == "__main__":
    run()
