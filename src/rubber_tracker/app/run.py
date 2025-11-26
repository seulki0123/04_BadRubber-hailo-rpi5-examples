from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

from rubber_tracker.camera import IPCamera
from rubber_tracker.id_manager import IDManager
from rubber_tracker.detection import DetectionCallback, DetectionQueue
from rubber_tracker.processing import PostProcessor
from rubber_tracker.utils import Drawer, ActiveListener
from rubber_tracker.network import NetworkEventHub

def run():

    # 1. Network Event Hub & ID Manager
    network_event_hub = NetworkEventHub()
    id_manager = IDManager()

    network_event_hub.add_listener_callback(id_manager.add_exit_id)
    id_manager.add_exit_callback(network_event_hub.notify)

    network_event_hub.start()

    # 3. open cameras
    cam = IPCamera()
    cam.open_cameras()
    
    # 4. create app
    detection_queue = DetectionQueue()
    app_callback = DetectionCallback()
    app = GStreamerDetectionApp(app_callback, detection_queue, cam.target_w, cam.target_h, cam.video_sink)

    # 5. Drawer
    drawer = Drawer(
        stream_status_getter=cam.get_stream_status,
        tracks_info_getter=id_manager.get_tracks_info,
        masks_getter=id_manager.get_masks,
        message_getter=id_manager.get_messages,
    )

    # 6. start post processor threads
    post_processor = PostProcessor(
        queue_getter=detection_queue.get,
        track_in_exit_zone_getter=id_manager.get_track_in_exit_zone,
        track_created_callback=id_manager.track_created_callback,
        track_removed_callback=id_manager.track_removed_callback,
        draw_callback=drawer.draw,
    )
    post_processor.start_thread()

    # 7. set appsrc and start camera threads
    cam.set_appsrc(app.pipeline)
    cam.start_threads()

    # 8. add threads to app thread(Temporary)
    # TODO: Remove direct dependencies on these objects and their internal attributes.
    app.threads.append(drawer.recorder)

    # 9. add key listener
    active_listener = ActiveListener(active_controller=id_manager.active_controller)
    active_listener.start_thread()

    # 10. run app
    app.run()

if __name__ == "__main__":
    run()