class FallbackService:
    """
    Simple fallback id generator (keeps parity with previously provided FallbackManager).
    """
    LEFT_PADDING = 6
    RIGHT_PADDING = 6

    def __init__(self):
        self._counters = {}

    def get_fallback_id(self, error_type: int) -> str:
        if error_type not in self._counters:
            self._counters[error_type] = 1
        serial = self._counters[error_type]
        self._counters[error_type] += 1
        left = f"{int(error_type):0{self.LEFT_PADDING}d}"
        right = f"{int(serial):0{self.RIGHT_PADDING}d}"
        return f"{left}_{right}"
