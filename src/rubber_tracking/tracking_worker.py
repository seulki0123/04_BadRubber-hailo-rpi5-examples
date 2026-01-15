from .information_manager import InformationManager
from .tracker import Tracker

from utils import ProcessLogger, CustomThread, Inbox
from detect import DetectionPacket, Frame, Bboxes
from interfaces.receiver import ReceiverPacket
from classify import ClassificationPacket

class TrackingWorker(ProcessLogger):
    def __init__(
        self,
        get_detections,
        get_externals,
        get_classifications,
        send_tracking_results,
        send_classification_targets,
    ):
        # logger
        super().__init__(self.__class__.__name__)
        ### get datas functions
        self.get_detections = get_detections
        self.get_externals = get_externals
        self.get_classifications = get_classifications
        #### Inboxes
        self.externals: Inbox[ReceiverPacket] = Inbox()
        self.classifications: Inbox[ClassificationPacket] = Inbox()
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

        reciver_packets: list[ReceiverPacket] = self.get_externals()
        classifications: list[ClassificationPacket] = self.get_classifications()
        self.externals.push(reciver_packets)
        self.classifications.push(classifications)

        ### tracking
        processed_externals = self.id_mapper.process(
            self.externals.snapshot(), self.classifications.snapshot()
        )

        tracking_results, classification_targets, used_externals, used_classifications = self.tracker.process(
            detection_packet, processed_externals
        )

        ### send datas
        self.send_tracking_results(tracking_results)
        self.send_classification_targets(classification_targets)

        ### feedback used items
        self.externals.ack(used_externals)
        self.classifications.ack(used_classifications)
    
        # logging
        self.log_debug(f"------")
        self.log_debug(f"DetectionPacket: {detection_packet}")
        self.log_debug(f"New Externals: {reciver_packets}")
        self.log_debug(f"New Classifications: {classifications}")
        self.log_debug(f"Existing Externals: {self.externals}")
        self.log_debug(f"Existing Classifications: {self.classifications}")

    def run(self):
        self.thread.start()