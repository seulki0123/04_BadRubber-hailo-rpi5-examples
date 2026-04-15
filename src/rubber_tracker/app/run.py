from rubber_tracker.camera import IPCamera
from rubber_tracker.detect import DetectionApp
from rubber_tracker.network import NetworkEventHub
from rubber_tracker.track import TrackManager, TrackEventHandler
from rubber_tracker.monitoring import Monitoring
from rubber_tracker.sync import SyncManager
from rubber_tracker.utils import Drawer

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

    app.create_pipeline(width, height, video_sink, TrackEventHandler(track_manager), drawer.draw)
    cam.set_appsrc(app.get_gst_pipeline())
    track_manager.add_callback(net.notify_flow)
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
    app.run()

if __name__ == "__main__":
    run()