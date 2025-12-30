import time
import cv2
import numpy as np
from picamera2 import Picamera2
import os
import subprocess
import gi
gi.require_version('Gst', '1.0')
from gi.repository import Gst, GLib, GObject

def disable_qos(pipeline):
    """
    Iterate through all elements in the given GStreamer pipeline and set the qos property to False
    where applicable.
    When the 'qos' property is set to True, the element will measure the time it takes to process each buffer and will drop frames if latency is too high.
    We are running on long pipelines, so we want to disable this feature to avoid dropping frames.
    :param pipeline: A GStreamer pipeline object
    """
    # Ensure the pipeline is a Gst.Pipeline instance
    if not isinstance(pipeline, Gst.Pipeline):
        print("The provided object is not a GStreamer Pipeline")
        return

    # Iterate through all elements in the pipeline
    it = pipeline.iterate_elements()
    while True:
        result, element = it.next()
        if result != Gst.IteratorResult.OK:
            break

        # Check if the element has the 'qos' property
        if 'qos' in GObject.list_properties(element):
            # Set the 'qos' property to False
            element.set_property('qos', False)
            print(f"Set qos to False for {element.get_name()}")

def get_usb_video_devices():
    """
    Get a list of video devices that are connected via USB and have video capture capability.
    """
    video_devices = [f'/dev/{device}' for device in os.listdir('/dev') if device.startswith('video')]
    usb_video_devices = []

    for device in video_devices:
        try:
            # Use udevadm to get detailed information about the device
            udevadm_cmd = ["udevadm", "info", "--query=all", "--name=" + device]
            result = subprocess.run(udevadm_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            output = result.stdout.decode('utf-8')

            # Check if the device is connected via USB and has video capture capabilities
            if "ID_BUS=usb" in output and ":capture:" in output:
                usb_video_devices.append(device)
        except Exception as e:
            print(f"Error checking device {device}: {e}")

    return usb_video_devices[0]

class app_callback_class:
    def __init__(self):
        self.frame_count = 0
        self.frame_queue = multiprocessing.Queue(maxsize=3)
        self.running = True

    def increment(self):
        self.frame_count += 1

    def get_count(self):
        return self.frame_count

    def set_frame(self, frame):
        if not self.frame_queue.full():
            self.frame_queue.put(frame)

    def get_frame(self):
        if not self.frame_queue.empty():
            return self.frame_queue.get()
        else:
            return None

def dummy_callback(pad, info, user_data):
    """
    A minimal dummy callback function that returns immediately.

    Args:
        pad: The GStreamer pad
        info: The probe info
        user_data: User-defined data passed to the callback

    Returns:
        Gst.PadProbeReturn.OK
    """
    return Gst.PadProbeReturn.OK


def picamera_thread(pipeline, video_width, video_height, video_format, picamera_config=None):
    appsrc = pipeline.get_by_name("app_source")
    appsrc.set_property("is-live", True)
    appsrc.set_property("format", Gst.Format.TIME)
    print("appsrc properties: ", appsrc)
    # Initialize Picamera2
    with Picamera2() as picam2:
        if picamera_config is None:
            # Default configuration
            main = {'size': (1280, 720), 'format': 'RGB888'}
            lores = {'size': (video_width, video_height), 'format': 'RGB888'}
            controls = {'FrameRate': 30}
            config = picam2.create_preview_configuration(main=main, lores=lores, controls=controls)
        else:
            config = picamera_config
        # Configure the camera with the created configuration
        picam2.configure(config)
        # Update GStreamer caps based on 'lores' stream
        lores_stream = config['lores']
        format_str = 'RGB' if lores_stream['format'] == 'RGB888' else video_format
        width, height = lores_stream['size']
        print(f"Picamera2 configuration: width={width}, height={height}, format={format_str}")
        appsrc.set_property(
            "caps",
            Gst.Caps.from_string(
                f"video/x-raw, format={format_str}, width={width}, height={height}, "
                f"framerate=30/1, pixel-aspect-ratio=1/1"
            )
        )
        picam2.start()
        frame_count = 0
        start_time = time.time()
        print("picamera_process started")
        while True:
            frame_data = picam2.capture_array('lores')
            # frame_data = np.random.randint(0, 255, (height, width, 3), dtype=np.uint8)
            if frame_data is None:
                print("Failed to capture frame.")
                break
            # Convert framontigue data if necessary
            frame = cv2.cvtColor(frame_data, cv2.COLOR_BGR2RGB)
            frame = np.asarray(frame)
            # Create Gst.Buffer by wrapping the frame data
            buffer = Gst.Buffer.new_wrapped(frame.tobytes())
            # Set buffer PTS and duration
            buffer_duration = Gst.util_uint64_scale_int(1, Gst.SECOND, 30)
            buffer.pts = frame_count * buffer_duration
            buffer.duration = buffer_duration
            # Push the buffer to appsrc
            ret = appsrc.emit('push-buffer', buffer)
            if ret != Gst.FlowReturn.OK:
                print("Failed to push buffer:", ret)
                break
            frame_count += 1