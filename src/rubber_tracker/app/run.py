from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

from rubber_tracker.camera import IPCamera
from rubber_tracker.id_manager import IDManager
from rubber_tracker.detection import DetectionCallback, DetectionQueue
from rubber_tracker.processing import PostProcessor
from rubber_tracker.utils import Drawer

def run():
    # 0. ID Manager
    id_manager = IDManager()
    id_manager.start_thread()

    # 1. open cameras
    cam = IPCamera()
    cam.open_cameras()
    
    # 2. create app
    detection_queue = DetectionQueue()
    app_callback = DetectionCallback()
    app = GStreamerDetectionApp(app_callback, detection_queue, cam.target_w, cam.target_h, cam.video_sink)

    # 3. Drawer
    drawer = Drawer(
        stream_status_getter=cam.get_stream_status,
        tracks_info_getter=id_manager.get_tracks_info,
        masks_getter=id_manager.get_masks,
        message_getter=id_manager.get_messages,
    )

    # 4. start post processor threads
    post_processor = PostProcessor(
        queue_getter=detection_queue.get,
        track_created_event=id_manager.track_created_event,
        track_removed_event=id_manager.track_removed_event,
        draw_callback=drawer.draw,
    )
    post_processor.start_thread()

    # 5. set appsrc and start camera threads
    cam.set_appsrc(app.pipeline)
    cam.start_threads()

    # 6. run app
    app.run()

if __name__ == "__main__":
    run()