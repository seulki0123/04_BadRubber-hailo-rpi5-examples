from rubber_tracker.camera import IPCamera
from rubber_tracker.detect import DetectionApp
from rubber_tracker.network import NetworkEventHub
from rubber_tracker.track import TrackManager, TrackEventHandler
from rubber_tracker.monitoring import Monitoring
from rubber_tracker.sync import SyncManager
from rubber_tracker.utils import Drawer
# 이벤트 이미지 저장 기능 (기본 disabled, config.event_image_saver.enabled 로 활성화)
from rubber_tracker.event_image_saver import FrameStore, ImageEventCapture, EventImageSaver

def run():
    cam = IPCamera()
    width, height, video_sink = cam.get_stream_settings()

    app = DetectionApp()
    net = NetworkEventHub()
    track_manager = TrackManager((width, height))
    sync_manager = SyncManager()
    drawer = Drawer(
        stream_status_getter=cam.get_stream_status,
        tracks_info_getter=track_manager.get_tracks_info,
        masks_getter=track_manager.get_masks,
        message_getter=track_manager.get_messages,
    )
    rsrc = Monitoring()

    # 이벤트 이미지 저장 배선:
    # 기존 TrackEventHandler 를 ImageEventCapture(FrameStore) 로 감싸서 on_updated
    # 시점의 프레임을 캐싱, 이후 track_manager 가 emit 하는 모든 이벤트가 동일 프레임을 참조.
    frame_store = FrameStore()
    image_saver = EventImageSaver(frame_store)
    event_handler = ImageEventCapture(TrackEventHandler(track_manager), frame_store)

    app.create_pipeline(width, height, video_sink, event_handler, drawer.draw)
    cam.set_appsrc(app.get_gst_pipeline())
    track_manager.add_callback(net.notify_flow)
    track_manager.add_callback(image_saver.on_event)  # 이벤트마다 이미지 저장 트리거
    net.add_listener_callback(track_manager.add_external_id)
    net.add_listener_callback(sync_manager.handle_replacing)

    track_manager.add_callback(sync_manager.add_external_time)
    track_manager.add_callback(sync_manager.add_internal_time)
    track_manager.add_callback(sync_manager.add_external_baler)
    track_manager.add_callback(sync_manager.add_internal_baler)
    sync_manager.add_callback(track_manager.on_sync)

    rsrc.run()
    net.run()
    cam.run()
    image_saver.start()  # 워커 스레드 기동 (disabled면 no-op)
    app.run()

if __name__ == "__main__":
    run()