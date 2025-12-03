# fallback_manager.py
class FallbackManager:
    """
    Generates fallback external IDs where:
      - left side = error_type (padded to 6 digits)
      - right side = per-type counter (padded to 6 digits, starts at 1)

    Example (error_type=1):
      000001_000001
      000001_000002
      000001_000003

    This ensures:
      - error types are obvious (left block)
      - counters are independent per error type (no cross-type mixing)
    """

    LEFT_PADDING = 6
    RIGHT_PADDING = 6

    def __init__(self):
        # per-error-type independent counters, start at 1
        # e.g. {1: 1, 2: 1, 3: 1}
        self._counters = {}

    def get_fallback_id(self, error_type: int) -> str:
        """
        Return an id like "000001_000001" where left is error_type and
        right is the per-type incrementing counter.
        """
        if error_type not in self._counters:
            # start counting from 1 as requested
            self._counters[error_type] = 1

        serial = self._counters[error_type]
        # increment for next call
        self._counters[error_type] += 1

        left = f"{int(error_type):0{self.LEFT_PADDING}d}"
        right = f"{int(serial):0{self.RIGHT_PADDING}d}"
        return f"{left}_{right}"
