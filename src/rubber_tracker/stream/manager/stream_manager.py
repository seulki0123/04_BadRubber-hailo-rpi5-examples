# stream/stream_manager.py
from datetime import datetime
from rubber_tracker.utils import load_config, ModuleLogger, delayed_call
from ..services.zone_flow_service import ZoneFlowService
from ..services.external_id_service import ExternalIdService
from ..services.track_controller import TrackController
from ..services.event_service import EventService
from ..services.fallback_service import FallbackService
from ..domain.track_registry import TrackRegistry
from ..infra.gates.gate_manager import GateManager
from ..infra.queues.queue_manager import QueueManager
from ..infra.validators.time_validator import TimeValidator
from ..services.speed_service import SpeedService
from ..services.capture_service import CaptureService
from rubber_tracker.utils.event_messages import EventMessage

class StreamManager(ModuleLogger):
    """
    Orchestrator: receives detections (created/updated/removed), coordinates services,
    and emits events via flow_callback.
    """
    def __init__(self, masksize):
        super().__init__(self.__class__.__name__)
        config = load_config()
        stream_cfg = config.get("stream", {})
        gates_cfg = config.get("gates", {})
        inputs = gates_cfg.get("inputs", [])
        zone_map = gates_cfg.get("map", {})
        weigher_delay = stream_cfg.get("weigher_delay", 0)

        # infra
        self.gates = GateManager(gates_cfg, masksize)
        self.queues = QueueManager(zones=inputs)
        self.validator = TimeValidator(zones=inputs)
        self.registry = TrackRegistry()
        self.fallback_manager = FallbackService()
        self.event_messages = EventMessage()

        # services
        self.zone_flow = ZoneFlowService(self.gates, gates_cfg.get("map", {}))
        self.external_id_service = ExternalIdService(self.queues, self.validator, zone_map)
        self.track_controller = TrackController(self.registry, self.fallback_manager, weigher_delay)
        self.event_service = EventService(self.event_messages)
        self.speed_service = SpeedService(stream_cfg.get("weigher_speed_threshold", 100))
        self.capture_service = CaptureService(str(stream_cfg.get("capture_dir")))

        # settings
        self.exit_event_when_removed = stream_cfg.get("exit_event_when_removed", True)
        self.capture_enabled = stream_cfg.get("capture_enabled", True)
        self.flow_callback = None

    # ------------------------------
    # External ID injection
    # ------------------------------
    def add_external_id(self, data):
        """Incoming network payload -> forward to external id service"""
        self.external_id_service.inject(data)

    # ------------------------------
    # Detection callbacks (from detector)
    # ------------------------------
    def on_created(self, track_id, bbox):
        # 1) get input zone
        zone = self.zone_flow.get_input_zone(bbox)
        if zone is None:
            self.log_warning(f"Track {track_id} not in any (active) input zone")
            return

        # 2) obtain valid ext id (may return None)
        data = self.external_id_service.pop_valid(zone)
        track = self.track_controller.create_track(track_id, zone, data)

        # send event
        evt = self.event_service.build_event(track.to_dict(), zone, event_type="created")
        self._emit_event(evt)

    def on_updated(self, track_id, bbox, frame):
        track = self.registry.get(track_id)
        if track is None:
            return

        # exit handling (optionally trigger when passing output)
        if not self.exit_event_when_removed:
            if self.zone_flow.get_output_zone(bbox):
                self.on_removed(track_id, bbox)
                return

        # weigher handling
        weigher_zone = self.zone_flow.get_weigher_zone(bbox)
        # if entered or exited, track_controller will provide events
        actions = self.track_controller.process_weigher(track, weigher_zone)
        for act in actions:
            evt = self.event_service.build_event(track.to_dict(), act["zone"], event_type=act["event_type"])

            if act["delay"]:
                delayed_call(func=self._emit_event, delay=act["delay"], args=(evt,))
            else:
                self._emit_event(evt)

        # update position/speed inside TrackState
        track.update_position(bbox)
        if self.capture_enabled\
            and weigher_zone\
            and self.speed_service.is_slow(track.speed):
            crop = self.capture_service.save_crop(
                track_id=track.track_id,
                speed=track.speed,
                bbox=bbox,
                frame=frame
            )

    def on_removed(self, track_id, bbox):
        track = self.registry.get(track_id)
        if track is None:
            return

        out_zone = self.zone_flow.get_output_zone(bbox)
        rejected = out_zone is None
        event_type = "exited" if not rejected else "removed"
        evt = self.event_service.build_event(track.to_dict(), out_zone, event_type=event_type, rejected=rejected)
        self._emit_event(evt)
        self.track_controller.remove_track(track_id)

    # ------------------------------
    # Helpers
    # ------------------------------
    def add_flow_callback(self, callback):
        self.flow_callback = callback

    def _emit_event(self, evt):
        if self.flow_callback:
            self.flow_callback(evt)

    # read-only helpers for external use
    def get_tracks_info(self, track_ids):
        return self.registry.dump_subset(track_ids)

    def get_masks(self):
        return self.gates.get_all_masks()

    def get_messages(self):
        return self.event_messages.get()
