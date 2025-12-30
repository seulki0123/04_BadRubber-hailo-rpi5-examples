import multiprocessing
import setproctitle
import signal
import os
import gi
import threading
import sys
import cv2
import numpy as np
import time
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib, GObject
from .gstreamer_helper_pipelines import get_source_type
from .utils import disable_qos, get_usb_video_devices, picamera_thread

class GStreamerApp:
    def __init__(
        self,
        user_data,
        video_source, # file, usb, rpi, libcamera, ximage, user_appsrc
        video_sink, # fakesink, ximagesink, filesink, appsink, autovideosink, ..
        video_width,
        video_height,
        disable_sync=False,
        show_fps=False,
        dump_dot=False,
        disable_callback=False,
    ):
        signal.signal(signal.SIGINT, self.shutdown)

        self.postprocess_dir = self._set_tappas_post_process_dir()

        self.user_data = user_data
        
        self.video_source= self._set_video_source(video_source)
        self.video_sink = video_sink
        self.video_width = video_width
        self.video_height = video_height

        self.show_fps = show_fps
        self.dump_dot = dump_dot
        self.disable_sync = disable_sync
        self.disable_callback = disable_callback

        self.source_type = get_source_type(self.video_source)
        self.pipeline = None
        self.loop = None
        self.threads = []
        self.error_occurred = False
        self.pipeline_latency = 300  # milliseconds

        # Set Hailo parameters; these parameters should be set based on the model used
        self.batch_size = 1
        self.video_format = "RGB"
        self.app_callback = None

        self.sync = "false" if (self.disable_sync or self.source_type != "file") else "true"
        self.show_fps = self.show_fps

        if self.dump_dot:
            os.environ["GST_DEBUG_DUMP_DOT_DIR"] = os.getcwd()

    def on_fps_measurement(self, sink, fps, droprate, avgfps):
        print(f"FPS: {fps:.2f}, Droprate: {droprate:.2f}, Avg FPS: {avgfps:.2f}")
        return True

    def create_pipeline(self):
        # Initialize GStreamer
        Gst.init(None)

        pipeline_string = self.get_pipeline_string()
        try:
            self.pipeline = Gst.parse_launch(pipeline_string)
        except Exception as e:
            print(f"Error creating pipeline: {e}", file=sys.stderr)
            sys.exit(1)

        # Connect to hailo_display fps-measurements
        if self.show_fps:
            print("Showing FPS")
            self.pipeline.get_by_name("hailo_display").connect("fps-measurements", self.on_fps_measurement)

        # Create a GLib Main Loop
        self.loop = GLib.MainLoop()

    def bus_call(self, bus, message, loop):
        t = message.type
        if t == Gst.MessageType.EOS:
            print("End-of-stream")
            self.on_eos()
        elif t == Gst.MessageType.ERROR:
            err, debug = message.parse_error()
            print(f"Error: {err}, {debug}", file=sys.stderr)
            self.error_occurred = True
            self.shutdown()
        # QOS
        elif t == Gst.MessageType.QOS:
            # Handle QoS message here
            qos_element = message.src.get_name()
            print(f"QoS message received from {qos_element}")
        return True


    def on_eos(self):
        if self.source_type == "file":
             # Seek to the start (position 0) in nanoseconds
            success = self.pipeline.seek_simple(Gst.Format.TIME, Gst.SeekFlags.FLUSH, 0)
            if success:
                print("Video rewound successfully. Restarting playback...")
            else:
                print("Error rewinding the video.", file=sys.stderr)
        else:
            self.shutdown()


    def shutdown(self, signum=None, frame=None):
        print("Shutting down... Hit Ctrl-C again to force quit.")
        signal.signal(signal.SIGINT, signal.SIG_DFL)
        self.pipeline.set_state(Gst.State.PAUSED)
        GLib.usleep(100000)  # 0.1 second delay

        self.pipeline.set_state(Gst.State.READY)
        GLib.usleep(100000)  # 0.1 second delay

        self.pipeline.set_state(Gst.State.NULL)
        GLib.idle_add(self.loop.quit)


    def get_pipeline_string(self):
        # This is a placeholder function that should be overridden by the child class
        return ""

    def dump_dot_file(self):
        print("Dumping dot file...")
        Gst.debug_bin_to_dot_file(self.pipeline, Gst.DebugGraphDetails.ALL, "pipeline")
        return False

    def run(self):
        # Add a watch for messages on the pipeline's bus
        bus = self.pipeline.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.bus_call, self.loop)


        # Connect pad probe to the identity element
        if not self.disable_callback:
            identity = self.pipeline.get_by_name("identity_callback")
            if identity is None:
                print("Warning: identity_callback element not found, add <identity name=identity_callback> in your pipeline where you want the callback to be called.")
            else:
                identity_pad = identity.get_static_pad("src")
                identity_pad.add_probe(Gst.PadProbeType.BUFFER, self.app_callback, self.user_data)

        hailo_display = self.pipeline.get_by_name("hailo_display")
        if hailo_display is None:
            print("Warning: hailo_display element not found, add <fpsdisplaysink name=hailo_display> to your pipeline to support fps display.")

        # Disable QoS to prevent frame drops
        disable_qos(self.pipeline)

        if self.source_type == "rpi":
            picam_thread = threading.Thread(target=picamera_thread, args=(self.pipeline, self.video_width, self.video_height, self.video_format))
            self.threads.append(picam_thread)
            picam_thread.start()

        # Set the pipeline to PAUSED to ensure elements are initialized
        self.pipeline.set_state(Gst.State.PAUSED)

        # Set pipeline latency
        new_latency = self.pipeline_latency * Gst.MSECOND  # Convert milliseconds to nanoseconds
        self.pipeline.set_latency(new_latency)

        # Set pipeline to PLAYING state
        self.pipeline.set_state(Gst.State.PLAYING)

        # Dump dot file
        if self.dump_dot:
            GLib.timeout_add_seconds(3, self.dump_dot_file)

        # Run the GLib event loop
        self.loop.run()

        # Clean up
        try:
            self.pipeline.set_state(Gst.State.NULL)
            for t in self.threads:
                t.join()
        except Exception as e:
            print(f"Error during cleanup: {e}", file=sys.stderr)
        finally:
            if self.error_occurred:
                print("Exiting with error...", file=sys.stderr)
                sys.exit(1)
            else:
                print("Exiting...")
                sys.exit(0)

    def _set_tappas_post_process_dir(self):
        tappas_post_process_dir = os.environ.get('TAPPAS_POST_PROC_DIR', '')
        if tappas_post_process_dir == '':
            print("TAPPAS_POST_PROC_DIR environment variable is not set. Please set it to by sourcing setup_env.sh")
            exit(1)
        return tappas_post_process_dir

    def _set_video_source(self, video_source):
        if video_source == 'usb':
            usb_video_devices = get_usb_video_devices()
            if not usb_video_devices:
                print('Provided argument "--input" is set to "usb", however no available USB cameras found. Please connect a camera or specifiy different input method.')
                exit(1)
            return usb_video_devices[0]
        return video_source