class FallbackService:
    """
    Simple fallback id generator (keeps parity with previously provided FallbackManager).
    1: create_fallback_baler_not_input_zone (trash)
    2: create_fallback_baler_no_externals
    """
    DEVICE_PADDING = 4
    ERROR_PADDING = 2
    RIGHT_PADDING = 6

    def __init__(self, device_id, create_fallback_baler_no_externals, create_fallback_baler_not_input_zone):
        self.device_id = device_id
        self._fallback_balers = {
            1: create_fallback_baler_not_input_zone,
            2: create_fallback_baler_no_externals,
        }
        self._counters = {}

    def get_fallback_id(self, error_type: int) -> tuple[int, str]:
        if error_type not in self._fallback_balers:
            self._fallback_balers[error_type] = 99
        if error_type not in self._counters:
            self._counters[error_type] = 1
        serial = self._counters[error_type]
        self._counters[error_type] += 1
        left = f"{int(self.device_id):0{self.DEVICE_PADDING}d}{int(error_type):0{self.ERROR_PADDING}d}"
        right = f"{int(serial):0{self.RIGHT_PADDING}d}"
        return self._fallback_balers[error_type], f"{left}_{right}"
