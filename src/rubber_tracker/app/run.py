from rubber_tracker.camera import IPCamera
from rubber_tracker.detect import DetectionApp

def run():
    cam = IPCamera()
    width, height, video_sink = cam.get_stream_settings()

    app = DetectionApp()
    app.create_pipeline(width, height, video_sink)
    cam.set_appsrc(app.get_gst_pipeline())

    cam.run()
    app.run()

if __name__ == "__main__":
    run()