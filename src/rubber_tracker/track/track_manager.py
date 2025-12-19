from datetime import datetime

from rubber_tracker.utils import load_config, ProcessLogger, delayed_call
from rubber_tracker.utils.event_messages import EventMessage

# Domain / Infra
from .domain.track_registry import TrackRegistry
from .infra.gates.gate_manager import GateManager
from .infra.queues.queue_manager import QueueManager

# Services - core
from .services.core.zone_flow_service import ZoneFlowService
from .services.core.track_controller import TrackController
from .services.core.event_service import EventService

# Services - external
from .services.external.id_service import ExternalIdService
from .services.external.fallback_service import FallbackService
from .services.external.validate_service import ExternalIdValidationService

# Services - state
from .services.state.speed_service import SpeedService
from .services.state.baler_service import BalerService
from .services.state.weigher_service import WeigherService

# Services - baler classify
from .services.classify.capture_service import CaptureService
from .services.classify.classify_service import BatchClassifyService

class TrackManager(ProcessLogger):
    """
    TrackManager: receives detections (created/updated/removed),
    coordinates services, and emits events via callbacks.
    """

    def __init__(self, masksize):
        super().__init__(self.__class__.__name__)

        # Load config
        config = load_config()
        stream_cfg = config.get("stream", {})
        gates_cfg = config.get("gates", {})
        cls_cfg = config.get("classifier", {})
        bbox_cfg = config.get("bbox_capture", {})
        baler_cfg = config.get("baler", {})

        inputs = gates_cfg.get("inputs", [])
        zone_map = gates_cfg.get("map", {})
        save_dir = bbox_cfg.get("save_dir", "results/captures")
        wr = bbox_cfg.get("wr", 2.0)
        hr = bbox_cfg.get("hr", 2.0)
        save = bbox_cfg.get("save", False)

        weigher_delay = stream_cfg.get("weigher_delay", 0)
        speed_threshold_min = stream_cfg.get("weigher_speed_threshold_min", 10)
        speed_threshold_max = stream_cfg.get("weigher_speed_threshold_max", 100)

        cls_model_path = cls_cfg.get("model_path", None)
        cls_class_names = cls_cfg.get("class_names", [])
        cls_imgsz = cls_cfg.get("imgsz", 24)
        cls_buffer_size = cls_cfg.get("buffer_size", 300)
        cls_limit = cls_cfg.get("cls_limit", 20)
        cls_conf_threshold = cls_cfg.get("conf_threshold", 0.95)

        unsynced_baler = baler_cfg.get("unsynced_baler", 10)
        create_fallback_baler = baler_cfg.get("create_fallback_baler", 10)
        classify_fallback_baler = baler_cfg.get("classify_fallback_baler", 10)

        # Infra Layer
        self.gates = GateManager(gates_cfg, masksize)
        self.queues = QueueManager(zones=inputs)
        self.registry = TrackRegistry()
        self.event_messages = EventMessage()

        # External Services
        self.validator = ExternalIdValidationService(zones=inputs)
        self.fallback_service = FallbackService()
        self.external_id_service = ExternalIdService(
            self.queues, self.validator, zone_map, self.fallback_service, unsynced_baler
        )

        # Weigher In/Out Services
        weigher_service = WeigherService(weigher_delay, zone_map)

        # Baler Classify Services
        classify_service = BatchClassifyService(cls_model_path, cls_class_names, cls_imgsz, cls_buffer_size)
        capture_service = CaptureService(wr, hr, save, save_dir)
        speed_service = SpeedService(speed_threshold_min, speed_threshold_max)
        baler_service = BalerService(
            speed_service=speed_service,
            classify_service=classify_service,
            capture_service=capture_service,
            cls_limit=cls_limit,
            cls_conf_threshold=cls_conf_threshold,
            track_map=self.registry.get_map(),
            on_baler_finalized=self.on_baler_finalized,
            classify_fallback_baler=classify_fallback_baler,
        )

        # Core Services
        self.zone_flow = ZoneFlowService(self.gates, zone_map)
        self.event_service = EventService(self.event_messages)

        self.track_controller = TrackController(
            registry=self.registry,
            fallback_service=self.fallback_service,
            weigher_service=weigher_service,
            baler_service=baler_service,
            create_fallback_baler=create_fallback_baler,
            classify_fallback_baler=classify_fallback_baler,
            unsynced_baler=unsynced_baler,
        )

        # Misc Settings
        self.exit_event_when_removed = stream_cfg.get("exit_event_when_removed", True)
        self.callbacks = []

        # sync
        self.synced_zones = []
        self.sync_offset = None

    # ------------------------------
    # External ID injection
    # ------------------------------
    def add_external_id(self, data):
        """Incoming network payload -> forward to external id service"""
        self.log_info(f"Adding external ID: {data}, synced zones: {self.synced_zones}")
        if not self.external_id_service.inject(data, self.synced_zones):
            return
        
        evt = self.event_service.build_event(data, data.get("zone"), event_type="id_added")
        self._emit_event(evt)

    # ------------------------------
    # Detection callbacks (from detector)
    # ------------------------------
    def on_created(self, track_id, bbox):
        # 0) check sync offset
        if self.sync_offset is not None and self.sync_offset > 0:
            self.sync_offset -= 1
            self.log_info(f"Ignored trash track {track_id}, remaining offset: {self.sync_offset}")
            return

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
        classify_zone = self.zone_flow.get_classify_zone(bbox)

        # if entered or exited, track_controller will provide events
        actions = self.track_controller.update_track(
            track=track,
            bbox=bbox,
            frame=frame,
            weigher_zone=weigher_zone,
            classify_zone=classify_zone
        )

        # emit weigher events
        for act in actions:
            evt = self.event_service.build_event(
                track.to_dict(), act["zone"], event_type=act["event_type"]
            )
            if act["delay"]:
                delayed_call(func=self._emit_event, delay=act["delay"], args=(evt,))
            else:
                self._emit_event(evt)

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

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def on_baler_finalized(self, track, event_type):
        evt = self.event_service.build_event(track.to_dict(), track.input_zone, event_type=event_type)
        self._emit_event(evt)

    def on_sync(self, offset, synced_zones):
        if self.sync_offset is not None and self.sync_offset > 0:
            self.log_info(f"Ignored sync offset: {self.sync_offset}")
            return
        
        self.sync_offset = offset

        if self.sync_offset is None:
            self.log_info(f"Sync offset is None", color="yellow")
            return

        if self.sync_offset < 0:
            self.synced_zones.clear()
            self.log_warning(f"Synced zones cleared", color="red")
            return

        added = []
        for z in synced_zones:
            if z not in self.synced_zones:
                self.synced_zones.append(z)
                added.append(z)

        self.log_info(f"Synced zones added: {added}; total={self.synced_zones}", color="green")

    # ------------------------------
    # Helpers

    def _emit_event(self, evt):
        for c in self.callbacks:
            c(evt)

    # read-only helpers for external use
    def get_tracks_info(self, track_ids):
        return self.registry.dump_subset(track_ids)

    def get_masks(self):
        return self.gates.get_all_masks()

    def get_messages(self):
        return self.event_messages.get()
