import json
import os
import threading


class FallbackService:
    """
    Simple fallback id generator (keeps parity with previously provided FallbackManager).
    1: create_fallback_baler_not_input_zone (trash)
    2: create_fallback_baler_no_externals
    """
    DEVICE_PADDING = 4
    ERROR_PADDING = 2
    RIGHT_PADDING = 6
    _lock = threading.Lock()

    def __init__(self, device_id, create_fallback_baler_no_externals, create_fallback_baler_not_input_zone, counter_dir, profile_id=None):
        self.device_id = device_id
        self.counter_file = os.path.join(counter_dir, f"{profile_id or 'default'}.json")
        self._fallback_balers = {
            1: create_fallback_baler_not_input_zone,
            2: create_fallback_baler_no_externals,
        }
        self._counters = self._load_counters()

    def get_fallback_id(self, error_type: int) -> tuple[int, str]:
        with self._lock:
            saved_counters = self._load_counters()
            if saved_counters != self._counters:
                print(
                    f"[WARNING] fallback counter file mismatch. "
                    f"use memory counters: memory={self._counters}, file={saved_counters}"
                )
            if error_type not in self._fallback_balers:
                self._fallback_balers[error_type] = 99
            if error_type not in self._counters:
                self._counters[error_type] = 1
            serial = self._counters[error_type]
            self._counters[error_type] += 1
            self._save_counters()
        left = f"{int(self.device_id):0{self.DEVICE_PADDING}d}{int(error_type):0{self.ERROR_PADDING}d}"
        right = f"{int(serial):0{self.RIGHT_PADDING}d}"
        return self._fallback_balers[error_type], f"{left}_{right}"

    def _load_counters(self):
        if not os.path.exists(self.counter_file):
            return {}
        with open(self.counter_file, "r", encoding="utf-8") as f:
            return {int(k): int(v) for k, v in json.load(f).items()}

    def _save_counters(self):
        directory = os.path.dirname(self.counter_file)
        if directory:
            os.makedirs(directory, exist_ok=True)
        with open(self.counter_file, "w", encoding="utf-8") as f:
            json.dump({str(k): v for k, v in self._counters.items()}, f)
