from .gate import Gate


class GateFactory:
    """Creates Gate objects using MaskLoader."""

    def __init__(self, loader, target_w, target_h):
        self.loader = loader
        self.w = target_w
        self.h = target_h

    def create(self, names):
        masks = self.loader.load_multi(names, self.w, self.h)
        return [Gate(name, masks[name]) for name in names]