from .gate import Gate

from .gate_factory import GateFactory
from ..utils.mask_loader import MaskLoader
from ..utils.config_watcher import ConfigWatcher
from rubber_tracker.utils import ProcessLogger, load_config
from rubber_tracker.detect.utils import Bboxes


class GateManager(ProcessLogger):
    def __init__(self, config=None, masksize=(640, 360)):
        super().__init__(self.__class__.__name__)
        config = config or load_config().get("gates", {})

        # Mask Loader
        loader = MaskLoader(config['mask_root'])
        self.factory = GateFactory(loader, masksize[0], masksize[1])

        # Gate objects
        self.input_gates = self.factory.create(config["inputs"])
        self.log_info(f"Input gates: {[g.name for g in self.input_gates]}")
        self.input_blocks = self.factory.create(config["input_blocks"])
        self.log_info(f"Input blocks: {[g.name for g in self.input_blocks]}")
        self.output_gates = self.factory.create(config["outputs"])
        self.log_info(f"Output gates: {[g.name for g in self.output_gates]}")
        self.weigher_gates = self.factory.create(config["weighers"])
        self.log_info(f"Weigher gates: {[g.name for g in self.weigher_gates]}")
        self.classify_gates = self.factory.create(config["classify"])
        self.log_info(f"Classify gates: {[g.name for g in self.classify_gates]}")

        # active flags
        active_file = config.get("active_file", "gate_active.yaml")
        self.active = {z: False for z in config["inputs"]}
        self.config_watcher = ConfigWatcher(active_file, self.set_active)

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
            if self.is_active(g.name) and g.bbox_hit_zone(bbox):
                return g.name
        return None
        
    def get_input_block_zone(self, bbox):
        for g in self.input_blocks:
            if g.bbox_hit_zone(bbox):
                return g.name
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

    def get_classify_zone(self, bbox):
        center = Bboxes.get_center(bbox)
        for g in self.classify_gates:
            if g.point_in_zone(center):
                return g.name
        return None

    def get_output_zones(self):
        return [g.name for g in self.output_gates]

    def get_all_masks(self):
        return [g.mask for g in self.input_gates + self.output_gates + self.weigher_gates + self.classify_gates]
