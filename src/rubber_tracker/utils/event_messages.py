import time

class EventMessage():
    def __init__(self):
        self.messages = {}
        self.message_timeout = 2

    def add(self, text, color):
        t0 = time.time()
        if text in self.messages:
            return
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