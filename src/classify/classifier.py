from .packet import ClassificationPacket

class Classifier:
    def __init__(self):
        pass

    def get_results(self) -> list[ClassificationPacket]:
        return []

    def add_classification_targets(self, classification_targets):
        pass
        
    def run(self):
        print("Classifier running")
