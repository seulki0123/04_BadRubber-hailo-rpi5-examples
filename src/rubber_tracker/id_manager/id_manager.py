from copy import deepcopy

import yaml

from .queue import Queue
from .gate import Gate
from .id_fetcher import IDFetcher
from .event_pusher import EventPusher

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

        default_active = config["gates"]["default_active"]

        # in-out map
        self.in_to_out_map = config["gates"]["map"]

        # id fetcher
        self.id_fetcher = IDFetcher(event_callback=self.id_fetcher_event)

        # event pusher
        self.event_pusher = EventPusher()

        # gate
        self.in_gate = Gate(name_in1, name_in2)
        self.out_gate = Gate(name_out1, name_out2)

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
            # }
        }

        self.event_messages = EventMessage()

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

    def id_fetcher_event(self, ext_id, from_zone, time):
        target_zone = self.in_to_out_map[from_zone]
        if not target_zone in self.in_queues:
            return self.log_error(f"Target Zone {target_zone} (from: {from_zone}) not found in id_queues")

        self.in_queues[target_zone].add(ext_id)
        # self.log_info(f"Added External ID {ext_id} to input zone {target_zone} (from: {from_zone})")

    def track_created_event(self, track_id, bbox):
        name = self.in_gate.is_in_zone(bbox)
        if name is None:
            self.log_info(f"Track {track_id} is not in any input zone")
            return

        if not self.in_active[name]:
            self.log_info(f"Input zone {name} is not activated")
            return
        
        ext_id = self.in_queues[name].get()
        if ext_id is None:
            self.log_error(f"No Avaliable External ID for Track {track_id} on input zone {name}")
            return
        
        self.ids[track_id] = {
            "ext_id": ext_id,
            "input": name,
            "color": generate_color(),
        }

        self.log_info(f"□■■ Track '{track_id}' →  ExtID '{ext_id}' ({name})")
            
    def track_removed_event(self, track_id, bbox):
        if track_id not in self.ids:
            return

        input_zone = self.ids[track_id]['input']
        output_zone = self.out_gate.is_in_zone(bbox)
        rejected = output_zone is None

        ext_id = self.ids[track_id]['ext_id']
        color = self.ids[track_id]['color']

        if not rejected:
            msg = f"■□■ '{track_id}/{ext_id}/{input_zone}' Exited to '{output_zone}'"
        
        else:
            msg = f"■■□ '{track_id}/{ext_id}/{input_zone}' Rejected"
        
        self.event_pusher.broadcast(ext_id, output_zone, rejected)
        
        self.log_info(msg)
        self.event_messages.add(msg, color)

        del self.ids[track_id]

    def get_tracks_info(self, track_ids):
        return deepcopy(self.ids)
    
    def get_masks(self):
        return list(self.in_gate.masks.values()) + list(self.out_gate.masks.values())

    def get_messages(self):
        return self.event_messages.get()

    def get_track_in_exit_zone(self, bbox):
        return self.out_gate.is_in_zone(bbox)

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