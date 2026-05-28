from datetime import datetime, timedelta, timezone

from rubber_tracker.utils import ProcessLogger, load_config
from .id_mode import SyncMode

class ExternalIdValidationService(ProcessLogger):
    def __init__(self, config=None, zones=None):
        super().__init__(self.__class__.__name__)
        config = config or load_config().get("valid_time", {})
        self.local_tz = timezone(timedelta(hours=9))
        zones = zones or []

        self.time_thresholds = {
            z: {
                "enabled": config.get(z, {}).get("enabled"),
                "min_create_seconds": config.get(z, {}).get("min_create_seconds"),
                "max_create_seconds": config.get(z, {}).get("max_create_seconds"),
                "margin_seconds": config.get(z, {}).get("margin_seconds")
            } for z in zones
        }

    def _parse_time(self, t):
        """Incoming time is local Korean time without timezone info."""

        if isinstance(t, str):
            t = t.strip()

        # datetime 객체일 때 (naive → KST로 지정)
        if isinstance(t, datetime):
            if t.tzinfo is None:
                return t.replace(tzinfo=self.local_tz)
            return t.astimezone(self.local_tz)

        # 문자열일 때 — 초까지만 포함: "YYYY-MM-DD HH:MM:SS"
        try:
            dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S")
            return dt.replace(tzinfo=self.local_tz)
        except:
            pass

        # 문자열일 때 — 밀리초까지 포함: "YYYY-MM-DD HH:MM:SS.sss"
        try:
            dt = datetime.strptime(t, "%Y-%m-%d %H:%M:%S.%f")
            return dt.replace(tzinfo=self.local_tz)
        except:
            pass

        self.log_error(f"Invalid time format: {t}")
        return None

    def validate(self, t0, zone, mode) -> tuple[bool, bool]:
        RET_VALID        = (True, False)   # valid, not discard
        RET_EARLY        = (False, False)  # early, not discard
        RET_DISCARD      = (False, True)   # discard
        
        t0 = self._parse_time(t0)
        if t0 is None:
            return RET_DISCARD

        # Current Korean time
        t1 = datetime.now(self.local_tz)
        dt = t1 - t0

        if zone not in self.time_thresholds:
            self.log_error(f"Zone '{zone}' not found in time thresholds")
            return RET_DISCARD

        zone_cfg = self.time_thresholds[zone]

        if not zone_cfg["enabled"]:
            self.log_info(f"Zone '{zone}' validation disabled")
            return RET_VALID

        mode = SyncMode(mode)
        lower_margin = zone_cfg["margin_seconds"][mode]["lower"]
        upper_margin = zone_cfg["margin_seconds"][mode]["upper"]
    
        min_cs = zone_cfg["min_create_seconds"] - lower_margin
        if dt < timedelta(seconds=min_cs):
            self.log_warning(f"[MIN CREATE] Too soon to assign ID in '{zone}': {dt} < {min_cs}s (margin: {lower_margin})")
            return RET_EARLY

        max_cs = zone_cfg["max_create_seconds"] + upper_margin
        if dt > timedelta(seconds=max_cs):
            self.log_error(f"[FORCED DISCARD] Data too old in '{zone}': {dt} > {max_cs}s (margin: {upper_margin})")
            return RET_DISCARD

        return RET_VALID

    def update_threshold(self, zone, min_cs, max_cs):
        """유동적 조정: zone 의 min/max_create_seconds 를 런타임에 갱신한다."""
        if zone not in self.time_thresholds:
            self.log_warning(f"[DynValidTime] zone '{zone}' not found, cannot update threshold")
            return

        prev_min = self.time_thresholds[zone]["min_create_seconds"]
        prev_max = self.time_thresholds[zone]["max_create_seconds"]

        self.time_thresholds[zone]["min_create_seconds"] = min_cs
        self.time_thresholds[zone]["max_create_seconds"] = max_cs

        self.log_info(
            f"[DynValidTime] '{zone}': "
            f"min {prev_min} → {min_cs:.2f}s, "
            f"max {prev_max} → {max_cs:.2f}s"
        )