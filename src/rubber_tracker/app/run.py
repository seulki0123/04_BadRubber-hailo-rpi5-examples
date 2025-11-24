from hailo_apps_infra.detection_pipeline import GStreamerDetectionApp

from rubber_tracker.camera import IPCamera
# from rubber_tracker.id_manager import IDManager
from rubber_tracker.detection.callback import DetectionCallback, UserData

def run():
    # 1. open cameras
    cam = IPCamera()
    cam.open_cameras()
    
    # 2. create app
    user_data = UserData(stream_status_getter=cam.get_stream_status)
    user_data.start_threads()
    
    app_callback = DetectionCallback()
    app = GStreamerDetectionApp(app_callback, user_data, cam.target_w, cam.target_h, cam.video_sink)

    # 3. set appsrc and start camera threads
    cam.set_appsrc(app.pipeline)
    cam.start_threads()

    # 4. run app
    app.run()

if __name__ == "__main__":
    run()