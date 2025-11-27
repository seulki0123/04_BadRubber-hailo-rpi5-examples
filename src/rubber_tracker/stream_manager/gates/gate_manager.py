from .gate import Gate

from .active_listener import ActiveListener
from rubber_tracker.utils import ModuleLogger, load_config
from rubber_tracker.detection.utils import Bboxes


class GateManager(ModuleLogger):
    def __init__(self, config=None):
        super().__init__(self.__class__.__name__)
        config = config or load_config().get("gates", {})

        mask_root = config.get("mask_root")

        inputs = config.get("inputs", [])
        outputs = config.get("outputs", [])
        weighers = config.get("weighers", [])
        default_active = config.get("default_active", True)

        # Gate objects
        self.input_gates = [Gate(name, mask_root) for name in inputs]
        self.output_gates = [Gate(name, mask_root) for name in outputs]
        self.weigher_gates = [Gate(name, mask_root) for name in weighers]

        # active flags
        self.active = {}
        for g in self.input_gates: # only input gates
            self.active[g.name] = default_active

        self.active_listener = ActiveListener(self.set_active)

    # ------------------------
    # Active control
    # ------------------------
    def set_active(self, zone, flag: bool):
        if zone not in self.active:
            self.log_error(f"Unknown zone: {zone}")
            return False
        self.active[zone] = flag
        self.log_info(f"Zone '{zone}' active={flag}")
        return True

    def is_active(self, zone):
        return self.active.get(zone, False)

    # ------------------------
    # Zone detection
    # ------------------------
    def get_input_zone(self, bbox):
        for g in self.input_gates:
            if g.bbox_hit_zone(bbox):
                return g.name if self.is_active(g.name) else None
        return None

    def get_output_zone(self, bbox):
        for g in self.output_gates:
            if g.bbox_hit_zone(bbox):
                return g.name
        return None

    def get_weigher_zone(self, bbox):
        center = Bboxes.get_center(bbox)
        for g in self.weigher_gates:
            if g.point_in_zone(center):
                return g.name
        return None

    def get_output_zones(self):
        return [g.name for g in self.output_gates]

    def get_all_masks(self):
        return [g.mask for g in self.input_gates + self.output_gates + self.weigher_gates]
