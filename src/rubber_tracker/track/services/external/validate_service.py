from datetime import datetime, timedelta, timezone

from rubber_tracker.utils import ProcessLogger, load_config

class ExternalIdValidationService(ProcessLogger):
    def __init__(self, config=None, zones=None, min_create_seconds=None, max_create_seconds=None):
        super().__init__(self.__class__.__name__)
        config = config or load_config().get("valid_time", {})
        self.validation_enabled = config.get("enabled", True)
        self.local_tz = timezone(timedelta(hours=9))
        self.min_create_seconds = min_create_seconds
        self.max_create_seconds = max_create_seconds
        zones = zones or []

        self.time_thresholds = {
            z: {
                "threshold": timedelta(seconds=config.get(z, {}).get("threshold", 0)),
                "error_margin": timedelta(seconds=config.get(z, {}).get("error_margin", 1000))
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

    def validate(self, t0, zone) -> tuple[bool, bool]:
        RET_VALID        = (True, False)   # valid, not discard
        RET_EARLY        = (False, False)  # early, not discard
        RET_DISCARD      = (False, True)   # discard
        
        t0 = self._parse_time(t0)
        if t0 is None:
            return RET_DISCARD

        # Current Korean time
        t1 = datetime.now(self.local_tz)
        dt = t1 - t0

        if self.min_create_seconds is not None:
            if dt < timedelta(seconds=self.min_create_seconds):
                self.log_warning(f"[MIN CREATE] Too soon to assign ID: {dt} < {self.min_create_seconds}s")
                return RET_EARLY

        if self.max_create_seconds is not None:
            if dt > timedelta(seconds=self.max_create_seconds):
                self.log_error(f"[FORCED DISCARD] Data too old: {dt} > {self.max_create_seconds}s")
                return RET_DISCARD

        if not self.validation_enabled:
            self.log_debug("Time validation disabled")
            return RET_VALID
        
        if zone not in self.time_thresholds:
            self.log_error(f"Zone '{zone}' not found in time thresholds")
            return RET_DISCARD



        threshold = self.time_thresholds[zone]["threshold"]
        error_margin = self.time_thresholds[zone]["error_margin"]
        min_t = threshold - error_margin
        max_t = threshold + error_margin

        # Too early
        if dt < min_t:
            self.log_warning(
                f"Yet to enter '{zone}'. Allowed window: {min_t} ~ {max_t} (current: {dt})"
            )
            return RET_EARLY

        # Too late
        if dt > max_t:
            self.log_error(
                f"Exceeded time threshold in '{zone}'. Allowed window: {min_t} ~ {max_t} (current: {dt})"
            )
            return RET_DISCARD

        self.log_info(f"Time validation passed for '{zone}'. Allowed window: {min_t} ~ {max_t} (current: {dt})")

        return RET_VALID