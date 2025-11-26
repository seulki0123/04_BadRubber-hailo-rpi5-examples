from copy import deepcopy
from datetime import datetime

import yaml

from .queue import Queue
from .gate import Gate

from rubber_tracker.utils import generate_color
from rubber_tracker.utils import ModuleLogger, CustomThread
from rubber_tracker.utils.event_messages import EventMessage

class IDManager(ModuleLogger):
    def __init__(self, config_path="config.yaml"):
        super().__init__(__class__.__name__)
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)

        name_in1 = config["gates"]["names"]["in1"]
        name_in2 = config["gates"]["names"]["in2"]
        name_out1 = config["gates"]["names"]["out1"]
        name_out2 = config["gates"]["names"]["out2"]
        name_weigher1 = config["gates"]["names"]["weigher1"]
        name_weigher2 = config["gates"]["names"]["weigher2"]

        default_active = config["gates"]["default_active"]

        # in/out map
        self.in_to_out_map = config["gates"]["map"]

        # exit callback
        self.exit_callback = None
        self.weigher_callback = None

        # gates
        self.in_gate = Gate(name_in1, name_in2)
        self.out_gate = Gate(name_out1, name_out2)
        self.weigher_gate = Gate(name_weigher1, name_weigher2)

        # queue
        self.in_queues = self._set_queues(name_in1, name_in2)

        # active
        self.in_active = self._set_active(name_in1, name_in2, default_active)
        self.name_in1 = name_in1
        self.name_in2 = name_in2

        # thread interval
        self.thread_interval = config["idmanager"]["thread_interval"]

        # ids
        self.ids = {
            # track_id: {
            #     "ext_id": ext_id,
            #     "input": input,
            #     "color": color,
            #     "measured": False
            # }
        }

        self.event_messages = EventMessage()

    def add_exit_id(self, data):
        if not self._valid_data(data):
            return
        
        ext_id, from_zone, target_zone = self._parse_data(data)
        
        if not target_zone in self.in_queues:
            return self.log_error(f"Target Zone {target_zone} (from: {from_zone}) not found in id_queues")

        self.in_queues[target_zone].add(ext_id)

    def track_created_callback(self, track_id, bbox):
        # zone
        name = self.in_gate.bbox_hit_zone(bbox)
        if name is None:
            self.log_info(f"Track {track_id} is not in any input zone")
            return

        # active
        if not self.in_active[name]:
            self.log_info(f"Input zone {name} is not activated")
            return
        
        # get ext_id
        ext_id = self.in_queues[name].get()
        if ext_id is None:
            self.log_error(f"No Avaliable External ID for Track {track_id} on input zone {name}")
            return
        
        # add id
        self._add_id(track_id, ext_id, name)
        
        # log
        self.log_info(f"□■■■ Track '{track_id}' →  ExtID '{ext_id}' ({name})")

    def track_weigher_callback(self, track_id, center):
        # check
        if track_id not in self.ids:
            return

        # zone
        weigher_zone = self.weigher_gate.point_in_zone(center)
        if weigher_zone is not None:
            self._track_in_weigher(track_id, weigher_zone)
        else:
            self._track_not_in_weigher(track_id)

    def _track_in_weigher(self, track_id, weigher_zone):
        if self.ids[track_id]['measured']:
            return
        
        # weigher callback
        ext_id = self.ids[track_id]['ext_id']
        color = self.ids[track_id]['color']
        self.weigher_callback(self._build_data(ext_id, weigher_zone))

        # update
        self.ids[track_id]['measured'] = True

        # log
        msg = f"■□■■ '{track_id}/{ext_id}' Entered to Weigher '{weigher_zone}'"
        self.log_info(msg)
        self.event_messages.add(msg, color)

    def _track_not_in_weigher(self, track_id):
        if not self.ids[track_id]['measured']:
            return
        
        # reset
        self.ids[track_id]['measured'] = False

        # log
        msg = f"■■□■ '{track_id}' Reset measured flag"
        self.log_info(msg)
        self.event_messages.add(msg, self.ids[track_id]['color'])

    def track_removed_callback(self, track_id, bbox):
        # check
        if track_id not in self.ids:
            return

        # zone
        input_zone = self.ids[track_id]['input']
        output_zone = self.out_gate.bbox_hit_zone(bbox)
        rejected = output_zone is None
    
        # exit callback
        ext_id = self.ids[track_id]['ext_id']
        color = self.ids[track_id]['color']

        if not rejected:
            msg = f"■■■□ '{track_id}/{ext_id}/{input_zone}' Exited to '{output_zone}'"
        else:
            msg = f"■■■■ '{track_id}/{ext_id}/{input_zone}' Rejected"
        
        self.exit_callback(self._build_data(ext_id, output_zone, rejected))
        
        # remove id
        self._remove_id(track_id)

        # log
        self.log_info(msg)
        self.event_messages.add(msg, color)

    def _set_queues(self, name1, name2):
        return {
            name1: Queue(name1) if name1 is not None else None,
            name2: Queue(name2) if name2 is not None else None,
        }

    def _set_active(self, name1, name2, default_active):
        return {
            name1: default_active,
            name2: default_active,
        }
    
    def _add_id(self, track_id, ext_id, input_zone):
        self.ids[track_id] = {
            "ext_id": ext_id,
            "input": input_zone,
            "color": generate_color(),
            "measured": False,
        }

    def _remove_id(self, track_id):
        del self.ids[track_id]

    def _valid_data(self, data):
        if "id" not in data or "zone" not in data or "time" not in data:
            self.log_error(f"Invalid data: {data}")
            return False
        return True

    def _parse_data(self, data):
        return data["id"], data["zone"], self.in_to_out_map[data["zone"]]

    def _build_data(self, ext_id, zone, rejected=False):
        return {
            "id": ext_id,
            "zone": zone,
            "rejected": rejected,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        }

    #########################################################
    def add_exit_callback(self, callback):
        self.exit_callback = callback
    
    def add_weigher_callback(self, callback):
        self.weigher_callback = callback

    def get_tracks_info(self, track_ids):
        return deepcopy(self.ids)
    
    def get_masks(self):
        return list(self.in_gate.masks.values()) + list(self.out_gate.masks.values()) + list(self.weigher_gate.masks.values())

    def get_messages(self):
        return self.event_messages.get()

    def get_track_in_exit_zone(self, bbox):
        return self.out_gate.bbox_hit_zone(bbox)
    
    def get_track_in_weigher_zone(self, center):
        return self.weigher_gate.point_in_zone(center)

    def active_controller(self, zone, active):
        if zone == "in1":
            self.in_active[self.name_in1] = active
            self.log_info(f"INPUT GATE 1 ACTIVATED {active} ({self.name_in1})")
        elif zone == "in2":
            self.in_active[self.name_in2] = active
            self.log_info(f"INPUT GATE 2 ACTIVATED {active} ({self.name_in2})")
        else:
            self.log_error("Invalid zone")
            return