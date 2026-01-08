from detect import Detector
from classify import Classifier
from interfaces.receiver import Receiver
from interfaces.sender import Sender
from rubber_tracking import TrackingWorker

def main():
    # initialize worker threads
    detector = Detector()
    receiver = Receiver()
    classifier = Classifier()
    sender = Sender()
    tracker = TrackingWorker(
        get_detections=detector.get_results,
        get_external_ids=receiver.get_external_ids,
        get_classification_results=classifier.get_results,
        send_tracking_results=sender.send_tracking_results,
        send_classification_targets=classifier.add_classification_targets,
    )

    # start worker threads
    detector.run()
    receiver.run()
    classifier.run()
    tracker.run()

if __name__ == "__main__":
    main()