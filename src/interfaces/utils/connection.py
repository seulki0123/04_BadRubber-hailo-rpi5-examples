from abc import ABC, abstractmethod

class Connection(ABC):
    @abstractmethod
    def send(self, data):
        pass

    def add_callback(self, callback):
        pass