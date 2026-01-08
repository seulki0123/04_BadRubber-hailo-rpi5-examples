from interfaces.video import VideoSource, FramePacket
from utils import load_config, ProcessLogger, CustomThread

class Detector(ProcessLogger):
    def __init__(self):
        super().__init__(self.__class__.__name__)
        config = load_config()

        self.video_sources: list[VideoSource] = []
        self._set_inputs(config["detect"]["sources"])
        self.thread = CustomThread(name=self.__class__.__name__, task=self._task, interval=0.0)

    def get_results(self):
        pass

    def run(self):
        self.start()
        for video_source in self.video_sources:
            video_source.start()
        print("Detector running")
        
    def start(self):
        self.thread.start()

    def stop(self):
        self.thread.stop()
        for video_source in self.video_sources:
            video_source.stop()

    def _task(self):
        for video_source in self.video_sources:
            frame_packet = video_source.get_frame()
            if frame_packet is None:
                continue
            print(frame_packet)

    def _set_inputs(self, sources):
        for source in sources:
            video_source = VideoSource(source)
            self.video_sources.append(video_source)
            self.log_info(f"Added video source: {video_source}")