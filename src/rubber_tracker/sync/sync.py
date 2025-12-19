from datetime import datetime
from rubber_tracker.utils import ProcessLogger, load_config
from .base import BaseSyncModel

class SyncManager(ProcessLogger):
    def __init__(self):
        super().__init__(self.__class__.__name__)
        cfg = load_config()

        # ---------- Time Sync ----------
        tcfg = cfg["sync"]["time"]
        if tcfg["enabled"]:
            self.time_sync = BaseSyncModel(
                "time",
                tcfg["max_queue_size"],
                tcfg["valid_queue_size"],
                tcfg["tolerance"],
            )
        else:
            self.time_sync = None

        self.time_event = {
            "external": tcfg["external_event_type"],
            "internal": tcfg["internal_event_type"],
        }

        self.time_active_target_zone = tcfg["active_target_zone"]

        # ---------- Baler Sync (A/B) ----------
        bcfg = cfg["sync"]["baler"]
        if bcfg["enabled"]:
            self.baler_sync = {
                "a": BaseSyncModel("baler_A", bcfg["max_queue_size"], bcfg["valid_queue_size"], bcfg["tolerance"], bcfg["mismatch"]),
                "b": BaseSyncModel("baler_B", bcfg["max_queue_size"], bcfg["valid_queue_size"], bcfg["tolerance"], bcfg["mismatch"]),
            }
        else:
            self.baler_sync = {"a": None, "b": None}

        # event 타입 매핑
        self.baler_event = {
            "external": {
                "a": bcfg["a"]["external_event_type"],
                "b": bcfg["b"]["external_event_type"],
            },
            "internal": {
                "a": bcfg["a"]["internal_event_type"],
                "b": bcfg["b"]["internal_event_type"],
            },
        }

        self.baler_active_target_zone = {
            "a": bcfg["a"]["active_target_zone"],
            "b": bcfg["b"]["active_target_zone"],
        }

        self.callbacks = []

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

        event_type = data.get("type")
        time_str = data.get("time")
        data_id = data.get("id")
        if data_id is None:
            self.log_warning(f"Time, {mode}: Data ID is missing: {data}")

        # event type mismatch → 무시
        if event_type != self.time_event[mode]:
            return

        if not time_str:
            self.log_error("Time data is missing")
            return

        parsed = self._parse_time(time_str)
        if parsed is None:
            return

        if mode == "external":
            self.time_sync.add_external(data_id, parsed)
        else:
            self.time_sync.add_internal(data_id, parsed)
            offset = self.time_sync.sync(mode="diff")
            self.log_info(f"Time synced result: {offset}")

            for cb in self.callbacks:
                cb(offset, self.time_active_target_zone)

    # ---------------------------
    # Baler
    # ---------------------------
    def add_external_baler(self, data):
        self._add_baler(data, mode="external")

    def add_internal_baler(self, data):
        self._add_baler(data, mode="internal")

    def _add_baler(self, data, mode):
        # a / b 각각 독립적으로 체크해야 함
        event_type = data.get("type")
        value_key = "input_baler" if mode == "external" else "final_baler"
        baler = data.get(value_key)
        data_id = data.get("id")
        if data_id is None:
            self.log_warning(f"Baler, {mode}: Data ID is missing: {data}")

        for key in ("a", "b"):
            sync_model = self.baler_sync[key]  # None이면 비활성

            # 비활성 키는 스킵
            if sync_model is None:
                continue

            # event type 매칭 안 되면 스킵
            if event_type != self.baler_event[mode][key]:
                continue

            # 값 없음 → 오류
            if baler is None:
                self.log_error(f"Baler, {mode}: Data missing for event type: {event_type}")
                return

            # ----- Add -----
            if mode == "external":
                sync_model.add_external(data_id, baler)
            else:
                sync_model.add_internal(data_id, baler)
                offset = sync_model.sync(mode="strict")
                self.log_info(f"Baler synced result({key}): {offset}")

                for cb in self.callbacks:
                    cb(offset, self.baler_active_target_zone[key])
            return
    # ---------------------------
    # Callback
    # ---------------------------
    def add_callback(self, callback):
        self.callbacks.append(callback)

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