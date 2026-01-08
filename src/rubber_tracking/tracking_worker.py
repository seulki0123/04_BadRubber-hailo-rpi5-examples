from .information_manager import InformationManager
from .tracker import Tracker

from utils import ProcessLogger, CustomThread
from detect import DetectionPacket, Frame, Bboxes

class TrackingWorker(ProcessLogger):
    def __init__(
        self,
        get_detections,
        get_external_ids,
        get_classification_results,
        send_tracking_results,
        send_classification_targets,
    ):
        ### get datas functions
        self.get_detections = get_detections
        self.get_external_ids = get_external_ids
        self.get_classification_results = get_classification_results
        ### tracking objects
        self.id_mapper = InformationManager()
        self.tracker = Tracker()
        ### send datas functions
        self.send_tracking_results = send_tracking_results
        self.send_classification_targets = send_classification_targets
        ### worker thread
        self.thread = CustomThread(name=self.__class__.__name__, task=self.task, interval=0.0)
        
    def task(self):
        ### get datas
        detection_packet: DetectionPacket | None = self.get_detections()
        if detection_packet is None:
            return
        
        frame_id: int = detection_packet.frame_id
        frame: Frame = detection_packet.frame
        bboxes: Bboxes = detection_packet.bboxes

        external_ids = self.get_external_ids()
        classification_results = self.get_classification_results()

        ### tracking
        processed_external_data = self.id_mapper.process(
            external_ids, classification_results
        )

        tracking_results, classification_targets = self.tracker.process(
            detection_packet, processed_external_data
        )

        ### send datas
        self.send_tracking_results(tracking_results)
        self.send_classification_targets(classification_targets)
    
    def run(self):
        self.thread.start()