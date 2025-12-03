from datetime import datetime

from ..gates.gate_manager import GateManager
from ..queues.queue_manager import QueueManager
from ..tracks.fallback_manager import FallbackManager
from ..tracks.track_registry import TrackRegistry
from ..tracks.track_state import TrackState
from ..validator.time_validator import TimeValidator

from rubber_tracker.utils.event_messages import EventMessage
from rubber_tracker.utils import load_config
from rubber_tracker.utils import ModuleLogger, delayed_call


class StreamManager(ModuleLogger):
    """
    High-level orchestrator: assigns IDs, manages gate events, and triggers callbacks.
    """

    def __init__(self):
        super().__init__(self.__class__.__name__)
        config = load_config()
        gates_cfg = config.get("gates", {})
        inputs = gates_cfg.get("inputs", [])
        self.exit_event_when_removed = gates_cfg.get("exit_event_when_removed", True)

        # --- Core components ---
        self.gates = GateManager(gates_cfg)
        self.queues = QueueManager(zones=inputs)
        self.validator = TimeValidator(zones=inputs)
        self.tracks = TrackRegistry()
        self.fallback_manager = FallbackManager()
        self.event_messages = EventMessage()

        # --- Settings ---
        self.zone_map = gates_cfg.get("map", {})
        self.weigher_wait_time = gates_cfg.get("weigher_wait_time", 0)

        # --- Callbacks ---
        self.flow_callback = None


    # ---------------------------------------------------------
    # external ID injection (from network)
    # ---------------------------------------------------------
    def add_external_id(self, data):
        required = {"id", "baler", "zone", "time"}
        missing = required - data.keys()
        if missing:
            self.log_error(f"Missing fields: {missing} in data {data}")
            return

        src = data.get("zone")
        dst = self.zone_map.get(src)

        if dst is None:
            self.log_error(f"From zone '{src}' not mapped in config")
            return
        
        if dst not in self.queues.get_all_zones():
            self.log_error(f"Target zone '{dst}' not found in queues")
            return

        data = self._build_data(data)
        if not self.queues.add_external_id(dst, data):
            return
        
        self.log_info(f"External ID '{data['id']}(baler: {data['baler']})' added to zone '{dst}'")


    # ---------------------------------------------------------
    # Track creation (input gate hit)
    # ---------------------------------------------------------
    def on_created(self, track_id, bbox):
        # 1. get input zone
        cur = self.gates.get_input_zone(bbox)
        if cur is None:
            self.log_warning(f"Track {track_id} not in any (active) input zone")
            return self._create_fallback_track(track_id, cur, 1)

        # 2. validate time
        peeked = self.queues.peek_next_id(cur)
        if peeked is None:
            self.log_error(f"No external ID (peek) for track {track_id} in zone '{cur}'")
            return self._create_fallback_track(track_id, cur, 2)

        valid, delete = self.validator.validate(peeked['time'], cur)
        if not valid:
            if delete:
                if self.queues.get_next_id(cur):
                    self.log_error(f"External ID '{peeked['id']}' deleted from zone '{cur}'")
                else:
                    self.log_error(f"Failed to delete external ID '{peeked['id']}' from zone '{cur}'")
            return self._create_fallback_track(track_id, cur, 3)
        
        # 3. get next external ID
        data = self.queues.get_next_id(cur)
        if data is None:
            self.log_error(f"No external ID for track {track_id} in zone '{cur}'")
            return self._create_fallback_track(track_id, cur, 2)
        
        # 4. register track
        track = TrackState(
            track_id=track_id,
            ext_id=data['id'],
            baler=data['baler'],
            input_zone=cur,
        )
        self.tracks.add(track)

        # 5. messages
        if self.flow_callback:
            self.flow_callback(
                self._build_event(track, cur)
            )

        msg = f"□■■■ Track Created: '{track.info}'"
        self.log_info(msg)
        self.event_messages.add(msg, track.color)


    # ---------------------------------------------------------
    # Track updated
    # ---------------------------------------------------------
    def on_updated(self, track_id, bbox):
        track = self.tracks.get(track_id)
        if track is None:
            return

        # exit handling
        if not self.exit_event_when_removed:
            if self.gates.get_output_zone(bbox):
                self.on_removed(track_id, bbox)

        # weigher handling
        cur = self.gates.get_weigher_zone(bbox)
        if cur:
            self._weigher_enter(track, cur)
        else:
            self._weigher_exit(track)


    # ---------------------------------------------------------
    # Track exit (output gate hit)
    # ---------------------------------------------------------
    def on_removed(self, track_id, bbox):
        track = self.tracks.get(track_id)
        if track is None:
            return
        
        cur = self.gates.get_output_zone(bbox)
        rejected = cur is None

        if self.flow_callback:
            self.flow_callback(
                self._build_event(track, cur, rejected)
            )
        
        self.tracks.remove(track_id)

        msg = (
            f"■■■□ Track Exited: '{track.info}' → '{cur}'"
            if not rejected
            else f"■■■■ Track Rejected: '{track.info}'"
        )
        self.log_info(msg)
        self.event_messages.add(msg, track.color)


    # ---------------------------------------------------------
    # Callbacks
    # ---------------------------------------------------------
    def add_flow_callback(self, callback):
        self.flow_callback = callback

    def _create_fallback_track(self, track_id, cur, error_type):
        fallback_id = self.fallback_manager.get_fallback_id(error_type)
        track = TrackState(
            track_id=track_id,
            ext_id=fallback_id,
            baler="",
            input_zone=cur,
            color=(0, 0, 0),
        )
        self.tracks.add(track)

        if self.flow_callback:
            self.flow_callback(self._build_event(track, cur))

        msg = f"□■■■ Track Created (FALLBACK {fallback_id}): '{track.info}'"
        self.log_warning(msg)
        self.event_messages.add(msg, track.color)

    # ---------------------------------------------------------
    # Internals
    # ---------------------------------------------------------
    def _weigher_enter(self, track, cur):
        if track.measured:
            return
        
        if self.flow_callback:
            delayed_call(
                func=self.flow_callback,
                delay=self.weigher_wait_time,
                args=(self._build_event(track, self.zone_map[cur]['in']),),
            )
        

        track.measured = True
        track.weigher_zone = cur

        msg = f"■□■■ Track Weighed: '{track.info}' in '{cur}'"
        delayed_call(
            func=self.event_messages.add,
            delay=self.weigher_wait_time,
            args=(msg, track.color),
        )
        self.log_info(msg)

    def _weigher_exit(self, track):
        if not track.measured:
            return

        cur = self.zone_map[track.weigher_zone]['out']
        if self.flow_callback:
            delayed_call(
                func=self.flow_callback,
                delay=self.weigher_wait_time,
                args=(self._build_event(track, cur),),
            )

        track.measured = False
        track.weigher_zone = None

        msg = f"■■□■ Track Weighed Reset: '{track.info}' in '{cur}'"
        delayed_call(
            func=self.event_messages.add,
            delay=self.weigher_wait_time,
            args=(msg, track.color),
        )
        self.log_info(msg)


    def _build_event(self, track, zone, rejected=False):
        return {
            'id': track.ext_id,
            'baler': track.baler,
            'zone': zone,
            'rejected': rejected,
            'time': datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
        }

    def _build_data(self, data):
        return {
            'id': data['id'],
            'baler': data['baler'],
            'time': data['time'],
        }

    # ---------------------------------------------------------
    # Utiles
    # ---------------------------------------------------------
    def get_tracks_info(self, track_ids):
        info = {}
        for tid in track_ids:
            t = self.tracks.get(tid)
            if t is not None:
                info[tid] = t.to_dict()
        return info

    def get_masks(self):
        return self.gates.get_all_masks()

    def get_messages(self):
        return self.event_messages.get()