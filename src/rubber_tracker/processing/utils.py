import time

from rubber_tracker.utils import ModuleLogger

class EventMessage(ModuleLogger):
    def __init__(self):
        super().__init__(self.__class__.__name__)
        self.messages = {}
        self.message_timeout = 2

    def add(self, texts, colors):
        t0 = time.time()
        for text, color in zip(texts, colors):
            if text is None:
                continue
            if text in self.messages:
                self.warning(f"Text {text} is already added")
                continue
            self.messages[text] = {"color": color, "t0": t0}

    def _remove(self):
        t1 = time.time()
        remove_texts = []
        for text, info in self.messages.items():
            if t1 - info["t0"] > self.message_timeout:
                remove_texts.append(text)
        for text in remove_texts:
            del self.messages[text]

    def get(self):
        self._remove()
        return list(self.messages.keys()), [info["color"] for info in self.messages.values()]