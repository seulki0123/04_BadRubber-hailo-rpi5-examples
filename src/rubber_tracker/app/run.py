from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

from rubber_tracker.camera import IPCamera
# from rubber_tracker.id_manager import IDManager
from rubber_tracker.detection import DetectionCallback, DetectionQueue
from rubber_tracker.processing import PostProcessor

def run():
    # 1. open cameras
    cam = IPCamera()
    cam.open_cameras()
    
    # 2. create app
    detection_queue = DetectionQueue()
    app_callback = DetectionCallback()
    app = GStreamerDetectionApp(app_callback, detection_queue, cam.target_w, cam.target_h, cam.video_sink)

    # 3. start post processor threads
    post_processor = PostProcessor(queue_getter=detection_queue.get, stream_status_getter=cam.get_stream_status)
    post_processor.start_thread()

    # 4. set appsrc and start camera threads
    cam.set_appsrc(app.pipeline)
    cam.start_threads()

    # 5. run app
    app.run()

if __name__ == "__main__":
    run()