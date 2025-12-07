from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

from rubber_tracker.camera import IPCamera
from rubber_tracker.orchestrator import Orchestrator, OrchestratorEventHandler
from rubber_tracker.detection import DetectionCallback, DetectionQueue
from rubber_tracker.processing import PostProcessor
from rubber_tracker.network import NetworkEventHub
from rubber_tracker.utils import Drawer

def run():

    # 1. open cameras
    cam = IPCamera()
    WIDTH = cam.target_w
    HEIGHT = cam.target_h
    VIDEO_SINK = cam.video_sink

    # 2. Network Event Hub & ID Manager
    network_event_hub = NetworkEventHub()
    orchestrator = Orchestrator(masksize=(WIDTH, HEIGHT))

    network_event_hub.add_listener_callback(orchestrator.add_external_id)
    orchestrator.add_flow_callback(network_event_hub.notify_flow)
    
    network_event_hub.start()
    
    # 3. create app
    detection_queue = DetectionQueue()
    app_callback = DetectionCallback()
    app = GStreamerDetectionApp(app_callback, detection_queue, WIDTH, HEIGHT, VIDEO_SINK)

    # 4. Drawer
    drawer = Drawer(
        stream_status_getter=cam.get_stream_status,
        tracks_info_getter=orchestrator.get_tracks_info,
        masks_getter=orchestrator.get_masks,
        message_getter=orchestrator.get_messages,
    )

    # 5. start post processor threads
    post_processor = PostProcessor(
        queue_getter=detection_queue.get,
        event_handler=OrchestratorEventHandler(orchestrator),
        draw_callback=drawer.draw,
    )
    post_processor.start_thread()

    # 6. set appsrc and start camera threads
    cam.set_appsrc(app.pipeline)
    cam.start_threads()

    # 7. add threads to app thread(Temporary)
    # TODO: Remove direct dependencies on these objects and their internal attributes.
    app.threads.append(drawer.recorder)

    # 8. run app
    app.run()

if __name__ == "__main__":
    run()