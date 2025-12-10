from rubber_tracker.camera import IPCamera
from rubber_tracker.detect import DetectionApp
from rubber_tracker.network import NetworkEventHub
from rubber_tracker.orchestrator import Orchestrator, OrchestratorEventHandler
from rubber_tracker.utils import Drawer

def run():
    cam = IPCamera()
    width, height, video_sink = cam.get_stream_settings()

    app = DetectionApp()
    net = NetworkEventHub()
    orchestrator = Orchestrator((width, height))
    drawer = Drawer(
        stream_status_getter=cam.get_stream_status,
        tracks_info_getter=orchestrator.get_tracks_info,
        masks_getter=orchestrator.get_masks,
        message_getter=orchestrator.get_messages,   
    )

    app.create_pipeline(width, height, video_sink, OrchestratorEventHandler(orchestrator), drawer.draw)
    cam.set_appsrc(app.get_gst_pipeline())
    orchestrator.add_flow_callback(net.notify_flow)
    net.add_listener_callback(orchestrator.add_external_id)

    net.run()
    cam.run()
    app.run()

if __name__ == "__main__":
    run()