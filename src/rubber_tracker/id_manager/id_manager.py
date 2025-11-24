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

        # id fetcher
        self.id_fetcher = IDFetcher(event_callback=self.id_fetcher_event)
        self.id_fetcher.connect()

        # event pusher
        self.event_pusher = EventPusher()
        self.event_pusher.start()

        # gate
        self.in_gate = Gate(name_in1, name_in2)
        self.out_gate = Gate(name_out1, name_out2)

        # queue
        self.in_queues = self._set_queues(name_in1, name_in2)

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
            name1: Queue(name1),
            name2: Queue(name2),
        }

    def start_thread(self):
        thread = CustomThread(name=self.__class__.__name__, task=self.id_fetcher.recv_loop, interval=self.thread_interval)
        thread.start()

    def id_fetcher_event(self, data):
        if data is None:
            return
            
        target = data["target"]
        if not target in self.in_queues:
            return self.log_error(f"Target {target} not found in id_queues")

        self.in_queues[target].add(data["id"])

    def track_created_event(self, track_id, bbox):
        name = self.in_gate.is_in_zone(bbox)
        if name is None:
            self.log_info(f"Track {track_id} is not in any input zone")
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

        self.log_info(f"Track {track_id} is assigned to External ID {ext_id} on input zone {name}")
            
    def track_removed_event(self, track_id, bbox):
        if track_id not in self.ids:
            return

        name = self.out_gate.is_in_zone(bbox)
        rejected = name is None

        ext_id = self.ids[track_id]['ext_id']
        color = self.ids[track_id]['color']

        if not rejected:
            msg = f"{track_id}/{ext_id}/{name} is exited"
        
        else:
            msg = f"{track_id}/{ext_id}/{name} is rejected"
        
        self.event_pusher.broadcast(ext_id, name, rejected)
        self.id_fetcher.send_event(ext_id, name, rejected)
        
        self.log_info(msg)
        self.event_messages.add(msg, color)

        del self.ids[track_id]

    def get_tracks_info(self, track_ids):
        return deepcopy(self.ids)
    
    def get_masks(self):
        return list(self.in_gate.masks.values()) + list(self.out_gate.masks.values())

    def get_messages(self):
        return self.event_messages.get()
