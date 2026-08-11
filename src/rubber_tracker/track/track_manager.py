import os
from datetime import datetime

from rubber_tracker.utils import load_config, ProcessLogger, delayed_call, LogColor
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
from .services.external.id_mode import IDModeManager
from .services.external.fallback_service import FallbackService
from .services.external.validate_service import ExternalIdValidationService
from .services.external.valid_time_adjuster import ValidTimeAdjuster

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

    def __init__(self, masksize, profile_id=None):
        # 멀티 프로파일에서 로그 출처 식별을 위해 logger 이름에 profile_id 를 포함한다.
        logger_name = self.__class__.__name__ if profile_id is None else f"{self.__class__.__name__}[{profile_id}]"
        super().__init__(logger_name)

        self.profile_id = profile_id

        # Load config
        config = load_config(profile_id)
        stream_cfg = config.get("stream", {})
        gates_cfg = config.get("gates", {})
        cls_cfg = config.get("classifier", {})
        bbox_cfg = config.get("bbox_capture", {})
        baler_cfg = config.get("baler", {})
        tracker_cfg = config.get("tracker", {})
        idmanager_cfg = config.get("idmanager", {})
        valid_time_cfg = config.get("valid_time", {})
        stream_queue_cfg = config.get("stream_queue", {})
        log_dir_cfg = config.get("log_dir", {})

        inputs = gates_cfg.get("inputs", [])
        zone_map = gates_cfg.get("map", {})
        save_dir = bbox_cfg.get("save_dir", "results/captures")
        wr = bbox_cfg.get("wr", 2.0)
        hr = bbox_cfg.get("hr", 2.0)
        save = bbox_cfg.get("save", False)

        weigher_delay = stream_cfg.get("weigher_delay", 0)
        speed_threshold_min = stream_cfg.get("weigher_speed_threshold_min", 10)
        speed_threshold_max = stream_cfg.get("weigher_speed_threshold_max", 100)
        weigher_must_finalized = stream_cfg.get("weigher_must_finalized", False)

        cls_model_path = cls_cfg.get("model_path", None)
        cls_class_names = cls_cfg.get("class_names", [])
        cls_imgsz = cls_cfg.get("imgsz", 24)
        cls_buffer_size = cls_cfg.get("buffer_size", 300)
        cls_limit = cls_cfg.get("cls_limit", 20)
        cls_conf_threshold = cls_cfg.get("conf_threshold", 0.95)

        unsynced_baler = baler_cfg.get("unsynced_baler", 11)
        create_fallback_baler_no_externals = baler_cfg.get("create_fallback_baler_no_externals", 10)
        classify_fallback_baler = baler_cfg.get("classify_fallback_baler", 12)
        create_fallback_baler_not_input_zone = baler_cfg.get("create_fallback_baler_not_input_zone", 13)

        self.create_retry_delay = idmanager_cfg.get("create_retry_delay", None)
        self.device_fallback_id = idmanager_cfg["device_fallback_id"]
        self.fallback_counter_dir = os.path.join(log_dir_cfg["root"], log_dir_cfg["fallback_counter"])

        self.track_age_threshold = tracker_cfg.get("age_threshold", 15)

        # Infra Layer
        self.gates = GateManager(gates_cfg, masksize)
        self.queues = QueueManager(config=stream_queue_cfg, zones=inputs)
        self.registry = TrackRegistry()
        self.event_messages = EventMessage()

        # External Services
        # 멀티 프로파일에서 valid_time 은 프로파일별로 다르므로 명시적으로 주입한다.
        self.id_mode_manager = IDModeManager()
        self.validator = ExternalIdValidationService(config=valid_time_cfg, zones=inputs)
        self.valid_time_adjuster = ValidTimeAdjuster(self.validator, valid_time_cfg)
        self.fallback_service = FallbackService(
            device_id=self.device_fallback_id,
            create_fallback_baler_no_externals=create_fallback_baler_no_externals,
            create_fallback_baler_not_input_zone=create_fallback_baler_not_input_zone,
            counter_dir=self.fallback_counter_dir,
            profile_id=self.profile_id,
        )
        self.external_id_service = ExternalIdService(
            self.queues, self.id_mode_manager, self.validator, zone_map, self.fallback_service, unsynced_baler
        )

        # Weigher In/Out Services
        weigher_service = WeigherService(weigher_delay, zone_map, weigher_must_finalized)

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
        event_cfg = config["event"]
        self.camera_id = str(config["camera_id"])
        self.event_service = EventService(
            self.event_messages,
            event_cfg=event_cfg,
            camera_id=self.camera_id,
        )

        self.track_controller = TrackController(
            registry=self.registry,
            fallback_service=self.fallback_service,
            weigher_service=weigher_service,
            baler_service=baler_service,
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
        # TODO: 메시지 타입별 라우팅을 상위 레이어(run.py 또는 별도 dispatcher)로 분리
        if data.get("type") == "wrapper_replacing":
            return

        if data.get("type") == "track_event_count_reset":
            cam = str(data.get("camera_id") or "")
            if cam == self.camera_id:
                self.event_service.apply_remote_reset(data.get("meta") or {})
            return

        if data.get("type") == "track_external_id_reset":
            self._handle_external_id_reset(data)
            return

        self.log_info(f"Adding external ID: {data}, synced zones: {self.synced_zones}")
        if not self.external_id_service.inject(data, self.synced_zones):
            return
        
        evt = self.event_service.build_event(data, data.get("zone"), event_type="id_added")
        self._emit_event(evt)

    # ------------------------------
    # Detection callbacks (from detector)
    # ------------------------------
    def on_created(self, track_id, bbox, conf, retry=False):
        # 0) check sync offset
        if self.sync_offset is not None and self.sync_offset > 0:
            self.sync_offset -= 1
            self.log_info(f"Ignored trash track {track_id}, remaining offset: {self.sync_offset}")
            return

        # 1) check input block zone
        block_zone = self.zone_flow.get_input_block_zone(bbox)
        if block_zone is not None:
            self.log_warning(f"Track {track_id} is in input block zone: {block_zone}")
            return

        # 2) get input zone
        zone = self.zone_flow.get_input_zone(bbox)
        if zone is None:
            fallback_case = 1
            data = None
            self.log_warning(f"Track {track_id} not in any (active) input zone")
        else:
            fallback_case = 2
            data = self.external_id_service.pop_valid(zone)
        
        if data is None and self.create_retry_delay is not None:
            if not retry:
                self.log_warning(f"[Retry] □□■■ '{track_id}' creating fallback track in '{zone}' after {self.create_retry_delay} seconds")
                delayed_call(
                    self.on_created,
                    delay=self.create_retry_delay,
                    args=(track_id, bbox, conf),
                    kwargs={"retry": True},
                )
                return
            else:
                self.log_warning(f"[Retry] □□■■ '{track_id}' failed to create fallback track in '{zone}'")

        track = self.track_controller.create_track(track_id, zone, data, fallback_case, bbox, conf)

        # send event
        evt = self.event_service.build_event(track.to_dict(), zone, event_type="created")
        self._emit_event(evt)

    def on_updated(self, track_id, bbox, frame, age):
        track = self.registry.get(track_id)
        if track is None:
            return

        # exit handling (optionally trigger when passing output)
        if not self.exit_event_when_removed:
            if self.zone_flow.get_output_zone(bbox):
                self.on_removed(track_id, bbox, age)
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

    def on_removed(self, track_id, bbox, age):
        track = self.registry.get(track_id)
        if track is None:
            return

        age = int(age)
        out_zone = self.zone_flow.get_output_zone(bbox)
        rejected = bool(out_zone is None or age < self.track_age_threshold)
        event_type = "exited" if not rejected else "removed"
        self.log_info(f"Track {track_id} on removed, age: {age}, rejected: {rejected}, event_type: {event_type}")
        evt = self.event_service.build_event(track.to_dict(), out_zone, event_type=event_type, rejected=rejected)
        self._emit_event(evt)
        self.track_controller.remove_track(track_id)

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def _handle_external_id_reset(self, data):
        scope = data.get("scope")

        if scope == "all":
            zones = self.queues.get_all_zones()
        elif scope == "zones":
            zones = data.get("zones") or []
            if not isinstance(zones, list):
                self.log_warning(f"track_external_id_reset: zones must be a list: {zones!r}")
                return
            if not zones:
                self.log_warning("track_external_id_reset: zones scope received with empty zones")
                return
        else:
            self.log_warning(f"track_external_id_reset: unknown scope: {scope!r}")
            return

        cleared = self.external_id_service.clear_ids_for_zones(zones)
        self.log_warning(
            f"track_external_id_reset applied: scope={scope}, zones={zones}, cleared={cleared}"
        )

    def on_baler_finalized(self, track, event_type):
        evt = self.event_service.build_event(track.to_dict(), track.input_zone, event_type=event_type)
        self._emit_event(evt)

    def on_time_match(self, zone, matched_pairs):
        """SyncManager.add_time_match_callback 으로 등록; valid_time 유동 조정에 사용."""
        self.valid_time_adjuster.on_match(zone, matched_pairs)

    def on_sync(self, offset, synced_zones):
        if self.sync_offset is not None and self.sync_offset > 0:
            self.log_info(f"Ignored sync offset: {self.sync_offset}")
            return
        
        self.sync_offset = offset

        if self.sync_offset is None:
            self.log_info(f"[SYNC] Sync offset is None", color=LogColor.YELLOW)
            return

        if self.sync_offset < 0:
            removed = []

            for z in synced_zones:
                if z in self.synced_zones:
                    self.synced_zones.remove(z)
                    removed.append(z)
            
            self.external_id_service.clear_ids_for_zones(synced_zones)

            self.log_warning(
                f"[SYNC] Synced zones removed: {removed}; remaining={self.synced_zones}",
                color=LogColor.RED
            )
            return

        added = []
        for z in synced_zones:
            if z not in self.synced_zones:
                self.synced_zones.append(z)
                added.append(z)

        self.log_info(f"[SYNC] Synced zones added: {added}; total={self.synced_zones}", color=LogColor.GREEN)

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
