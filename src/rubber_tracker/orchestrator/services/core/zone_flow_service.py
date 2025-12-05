class ZoneFlowService:
    """
    Thin adapter around GateManager + zone map config.
    Responsible for input/output/weigher zone resolution.
    """
    def __init__(self, gate_manager, zone_map=None):
        self.gates = gate_manager
        self.zone_map = zone_map or {}

    def get_input_zone(self, bbox):
        return self.gates.get_input_zone(bbox)

    def get_output_zone(self, bbox):
        return self.gates.get_output_zone(bbox)

    def get_weigher_zone(self, bbox):
        return self.gates.get_weigher_zone(bbox)

    def map_weigher_to_in(self, weigher_zone):
        if weigher_zone and weigher_zone in self.zone_map:
            return self.zone_map[weigher_zone].get('in')
        return None

    def map_weigher_to_out(self, weigher_zone):
        if weigher_zone and weigher_zone in self.zone_map:
            return self.zone_map[weigher_zone].get('out')
        return None
