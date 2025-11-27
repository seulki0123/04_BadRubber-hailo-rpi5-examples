from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

from rubber_tracker.camera import IPCamera
from rubber_tracker.stream_manager import StreamManager, StreamEventHandler
from rubber_tracker.detection import DetectionCallback, DetectionQueue
from rubber_tracker.processing import PostProcessor
from rubber_tracker.network import NetworkEventHub
from rubber_tracker.utils import Drawer

def run():

    # 1. Network Event Hub & ID Manager
    network_event_hub = NetworkEventHub()
    stream_manager = StreamManager()

    network_event_hub.add_listener_callback(stream_manager.add_external_id)
    stream_manager.add_flow_callback(network_event_hub.notify_flow)
    
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
        tracks_info_getter=stream_manager.get_tracks_info,
        masks_getter=stream_manager.get_masks,
        message_getter=stream_manager.get_messages,
    )

    # 6. start post processor threads
    post_processor = PostProcessor(
        queue_getter=detection_queue.get,
        stream_event_handler=StreamEventHandler(stream_manager),
        draw_callback=drawer.draw,
    )
    post_processor.start_thread()

    # 7. set appsrc and start camera threads
    cam.set_appsrc(app.pipeline)
    cam.start_threads()

    # 8. add threads to app thread(Temporary)
    # TODO: Remove direct dependencies on these objects and their internal attributes.
    app.threads.append(drawer.recorder)

    # 10. run app
    app.run()

if __name__ == "__main__":
    run()