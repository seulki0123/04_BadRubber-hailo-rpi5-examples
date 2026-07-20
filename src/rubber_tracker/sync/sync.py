from datetime import datetime
from rubber_tracker.utils import ProcessLogger, load_config
from .base import BaseSyncModel

class SyncManager(ProcessLogger):
    def __init__(self, profile_id=None):
        logger_name = self.__class__.__name__ if profile_id is None else f"{self.__class__.__name__}[{profile_id}]"
        super().__init__(logger_name)
        self.profile_id = profile_id
        cfg = load_config(profile_id)

        # ---------- Time Sync (Branch/Join A/Join B) ----------
        tcfg = cfg["sync"]["time"]
        time_keys = ("branch_in", "join_in_a", "join_in_b")
        time_names = {"branch_in": "time_branch", "join_in_a": "time_join_A", "join_in_b": "time_join_B"}

        self.time_sync = {}
        self.time_event = {"external": {}, "internal": {}}
        self.time_active_target_zone = {}

        for key in time_keys:
            zcfg = tcfg[key]
            if zcfg["enabled"]:
                self.time_sync[key] = BaseSyncModel(
                    time_names[key],
                    zcfg["max_queue_size"],
                    zcfg["valid_queue_size"],
                    zcfg["tolerance"],
                    zcfg["mismatch"],
                    zcfg["stale_external_suppress_max"],
                    zcfg["id_reset"],
                )
            else:
                self.time_sync[key] = None
            self.time_event["external"][key] = zcfg["external_event_type"]
            self.time_event["internal"][key] = zcfg["internal_event_type"]
            self.time_active_target_zone[key] = zcfg["active_target_zone"]

        # ---------- Baler Sync (Work A/Work B) ----------
        bcfg = cfg["sync"]["baler"]
        baler_keys = ("a", "b")
        baler_names = {"a": "baler_A", "b": "baler_B"}

        self.baler_sync = {}
        self.baler_event = {"external": {}, "internal": {}}
        self.baler_active_target_zone = {}

        for key in baler_keys:
            zcfg = bcfg[key]
            if zcfg["enabled"]:
                self.baler_sync[key] = BaseSyncModel(
                    baler_names[key],
                    zcfg["max_queue_size"],
                    zcfg["valid_queue_size"],
                    zcfg["tolerance"],
                    zcfg["mismatch"],
                    zcfg["stale_external_suppress_max"],
                    zcfg["id_reset"],
                )
            else:
                self.baler_sync[key] = None
            self.baler_event["external"][key] = zcfg["external_event_type"]
            self.baler_event["internal"][key] = zcfg["internal_event_type"]
            self.baler_active_target_zone[key] = zcfg["active_target_zone"]

        # ---------- Suspended (union of all suspension reasons) ----------
        self._paused_zones = set()
        self._speed_zones = set()
        self._suspended = set()

        # ---------- Speed check ----------
        self._last_external_time = {}
        self._speed_threshold = {}
        for key in time_keys:
            zcfg = tcfg[key]
            threshold = zcfg.get("min_external_interval")
            if threshold is not None:
                self._speed_threshold[key] = threshold

        # ---------- Callback ----------
        self.callbacks = []
        self.time_match_callbacks = []  # cb(zone, matched_pairs) called when time sync succeeds
        self.valid_mode_callbacks = []

    # ---------------------------
    # Suspended
    # ---------------------------
    def handle_pause(self, data):
        if data.get("type") != "wrapper_replacing":
            return
        zone = data.get("zone")
        if data.get("replacing", False):
            self._pause_zone(zone)
        else:
            self._resume_zone(zone)

    def _update_suspended(self):
        self._suspended = self._paused_zones | self._speed_zones

    def _reset_zone(self, zone):
        if zone in self.time_sync and self.time_sync[zone] is not None:
            self.time_sync[zone].reset_all()
        if zone in self.baler_sync and self.baler_sync[zone] is not None:
            self.baler_sync[zone].reset_all()

    # Pause Signal
    def _pause_zone(self, zone):
        self._paused_zones.add(zone)
        self._update_suspended()
        self._reset_zone(zone)
        self._emit_valid_mode(zone, "FIFO")
        self.log_info(f"[PAUSED] zone '{zone}' → queues reset, sync suspended")

    def _resume_zone(self, zone):
        self._paused_zones.discard(zone)
        self._update_suspended()
        self._emit_valid_mode(zone, "VALID")
        self.log_info(f"[RESUMED] zone '{zone}' → sync resumed")

    # Speed Status
    def _suspend_speed(self, zone, interval, threshold):
        if zone in self._speed_zones:
            return
        self._speed_zones.add(zone)
        self._update_suspended()
        self._reset_zone(zone)
        self._emit_valid_mode(zone, "FIFO")
        self.log_info(f"[SPEED] zone '{zone}' too fast ({interval:.2f}s < {threshold}s) → sync suspended")

    def _resume_speed(self, zone, interval):
        if zone not in self._speed_zones:
            return
        self._speed_zones.discard(zone)
        self._update_suspended()
        self._emit_valid_mode(zone, "VALID")
        self.log_info(f"[SPEED] zone '{zone}' speed normal ({interval:.2f}s) → sync resumed")

    def _check_speed(self, zone, parsed_time):
        threshold = self._speed_threshold.get(zone)
        if threshold is None:
            return

        last = self._last_external_time.get(zone)
        self._last_external_time[zone] = parsed_time

        if last is None:
            return

        interval = abs((parsed_time - last).total_seconds())

        if interval < threshold:
            self._suspend_speed(zone, interval, threshold)
        else:
            self._resume_speed(zone, interval)

    # ---------------------------
    # Time
    # ---------------------------
    def add_external_time(self, data):
        self._add_time(data, mode="external")

    def add_internal_time(self, data):
        self._add_time(data, mode="internal")

    def _add_time(self, data, mode):
        if self.time_sync is None:
            return

        event_type = data.get("event")
        time_str = data.get("time")
        data_id = data.get("id")
        if data_id is None:
            self.log_warning(f"Time, {mode}: Data ID is missing: {data}")

        if not time_str:
            self.log_error("Time data is missing")
            return

        parsed = self._parse_time(time_str)
        if parsed is None:
            return

        for key in ("branch_in", "join_in_a", "join_in_b"):
            sync_model = self.time_sync.get(key)

            if sync_model is None:
                continue

            if event_type != self.time_event[mode][key]:
                continue

            if mode == "external":
                self._check_speed(key, parsed)

            if key in self._suspended:
                continue

            if mode == "external":
                offset = sync_model.add_external(data_id, parsed)
                if offset == -1:
                    self._handle_time_sync_result(key, sync_model, offset)
            else:
                add_result = sync_model.add_internal(data_id, parsed)
                if add_result is None:
                    offset = sync_model.sync(mode="diff")
                    self._handle_time_sync_result(key, sync_model, offset)
                    return
                if add_result is False:
                    return

                offset = sync_model.sync(mode="diff")
                self._handle_time_sync_result(key, sync_model, offset)

            return

    # ---------------------------
    # Baler
    # ---------------------------
    def add_external_baler(self, data):
        self._add_baler(data, mode="external")

    def add_internal_baler(self, data):
        self._add_baler(data, mode="internal")

    def _add_baler(self, data, mode):
        # a / b 각각 독립적으로 체크해야 함
        event_type = data.get("event")
        value_key = "input_baler" if mode == "external" else "final_baler"
        baler = data.get(value_key)
        data_id = data.get("id")
        if data_id is None:
            self.log_warning(f"Baler, {mode}: Data ID is missing: {data}")

        for key in ("a", "b"):
            sync_model = self.baler_sync[key]

            if sync_model is None:
                continue

            if key in self._suspended:
                continue

            if event_type != self.baler_event[mode][key]:
                continue

            # 값 없음 → 오류
            if baler is None:
                if mode == "internal" and data_id is not None:
                    removed = sync_model.remove_external(data_id)
                    action = "removed" if removed else "was not present"
                    self.log_warning(
                        f"[SYNC] Baler internal ID '{data_id}' has no final_baler; "
                        f"external candidate {action}"
                    )
                else:
                    self.log_error(
                        f"Baler, {mode}: Data missing for event type: {event_type}"
                    )
                return

            # ----- Add -----
            if mode == "external":
                offset = sync_model.add_external(data_id, baler)
                if offset == -1:
                    self._handle_baler_sync_result(key, offset)
            else:
                add_result = sync_model.add_internal(data_id, baler)
                if add_result is None:
                    offset = sync_model.sync(mode="strict")
                    self._handle_baler_sync_result(key, offset)
                    return
                if not add_result:
                    return

                offset = sync_model.sync(mode="strict")
                self._handle_baler_sync_result(key, offset)
            return
    # ---------------------------
    # Callback
    # ---------------------------
    def _handle_time_sync_result(self, key, sync_model, offset):
        self.log_info(f"Time synced result({key}): {offset}")
        callback_offset = self._verified_offset_or_reset(offset)

        if callback_offset == 0:
            for cb in self.time_match_callbacks:
                cb(key, sync_model._last_matched_pairs)

        for cb in self.callbacks:
            cb(callback_offset, self.time_active_target_zone[key])

    def _handle_baler_sync_result(self, key, offset):
        self.log_info(f"Baler synced result({key}): {offset}")
        callback_offset = self._verified_offset_or_reset(offset)

        for cb in self.callbacks:
            cb(callback_offset, self.baler_active_target_zone[key])

    def add_callback(self, callback):
        self.callbacks.append(callback)

    def add_time_match_callback(self, callback):
        """cb(zone, matched_pairs) — sync 성공 시 매칭된 (ext_time, int_time) 쌍 전달."""
        self.time_match_callbacks.append(callback)

    def add_valid_mode_callback(self, callback):
        self.valid_mode_callbacks.append(callback)

    def _emit_valid_mode(self, zone, mode):
        for cb in self.valid_mode_callbacks:
            cb(zone, mode)

    def _verified_offset_or_reset(self, offset):
        if offset is None or offset <= 0:
            return offset

        self.log_warning(
            f"[SYNC] shifted offset {offset} is not fully verified; emitting -1 to reset external ids"
        )
        return -1

    # ---------------------------
    # Utils
    # ---------------------------
    def _parse_time(self, time_str):
        try:
            fmt = "%Y-%m-%d %H:%M:%S.%f" if "." in time_str else "%Y-%m-%d %H:%M:%S"
            return datetime.strptime(time_str, fmt)
        except ValueError as e:
            self.log_error(f"Invalid time format: {time_str} ({e})")
            return None
