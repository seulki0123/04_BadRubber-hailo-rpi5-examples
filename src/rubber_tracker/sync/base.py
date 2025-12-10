import queue
import threading
from rubber_tracker.utils import ModuleLogger


class BaseSyncModel(ModuleLogger):
    def __init__(self, name, max_queue_size, valid_queue_size, tolerance):
        super().__init__(self.__class__.__name__ + "_" + name)

        self.max_queue_size = max_queue_size
        self.valid_queue_size = valid_queue_size
        self.tolerance = tolerance

        self.externals = queue.Queue(maxsize=max_queue_size)
        self.internals = queue.Queue(maxsize=max_queue_size)

        self._external_lock = threading.Lock()
        self._internal_lock = threading.Lock()

    # Queue Reset
    def _reset_queue(self, q: queue.Queue, lock: threading.Lock):
        with lock, q.mutex:
            q.queue.clear()
            q.unfinished_tasks = 0
            q.all_tasks_done.notify_all()
            self.log_info("Queue reset")

    def reset_all(self):
        self._reset_queue(self.externals, self._external_lock)
        self._reset_queue(self.internals, self._internal_lock)

    # Put
    def _safe_put(self, q: queue.Queue, lock: threading.Lock, item):
        with lock:
            if q.full():
                self.log_warning("Queue full, ignoring item")
                return False
            try:
                q.put_nowait(item)
                return True
            except queue.Full:
                return False

    def add_external(self, external):
        self._safe_put(self.externals, self._external_lock, external)

    def add_internal(self, internal):
        self._safe_put(self.internals, self._internal_lock, internal)

    # Sync
    def _compare_values(self, a, b, tol):
        """raw/diff 모두 float or datetime을 지원."""
        try:
            diff = abs((a - b).total_seconds())
        except:
            diff = abs(a - b)
        return diff <= tol

    def _prefix_match_strict(self, ext_arr, int_arr):
        i = 0
        j = 0
        L_ext = len(ext_arr)
        L_int = len(int_arr)

        while i < L_ext and j < L_int:
            if ext_arr[i] == int_arr[j]:
                i += 1
                j += 1
            else:
                break
        return j

    def _prefix_match_diff(self, ext_arr, int_arr, tol):
        i = 0
        j = 0
        L_ext = len(ext_arr)
        L_int = len(int_arr)

        while i < L_ext and j < L_int:
            if self._compare_values(ext_arr[i], int_arr[j], tol):
                i += 1
                j += 1
            else:
                break
        return j

    def sync(self, mode="diff"):
        if not mode in ["diff", "strict"]:
            self.log_error(f"Invalid mode: {mode}")
            return
        
        externals = list(self.externals.queue)
        internals = list(self.internals.queue)

        if len(externals) < self.valid_queue_size or len(internals) < self.valid_queue_size:
            return

        # generate patterns
        if mode == "diff":
            ext_pattern = [(externals[i] - externals[i - 1]).total_seconds()
                           for i in range(1, len(externals))]
            int_pattern = [(internals[i] - internals[i - 1]).total_seconds()
                           for i in range(1, len(internals))]
        else:
            ext_pattern = externals
            int_pattern = internals

        L_ext = len(ext_pattern)
        L_int = len(int_pattern)

        max_len = min(L_ext, L_int)

        # suffix (internal) vs prefix (external)
        for match_len in range(max_len, self.valid_queue_size - 1, -1):

            ext_sub = ext_pattern[:match_len]
            int_sub = int_pattern[-match_len:]

            if mode == "diff":
                matched_len = self._prefix_match_diff(ext_sub, int_sub, self.tolerance)
            else:
                matched_len = self._prefix_match_strict(ext_sub, int_sub)

            if matched_len >= self.valid_queue_size:
                offset = L_int - matched_len

                self.log_info(
                    f"[SYNC/{mode}] matched_len={matched_len}, offset={offset}"
                )

                # remove stale internal!!!!!!!!!!!!!!!!!!!
                if offset > 0:
                    with self._internal_lock:
                        for _ in range(offset):
                            removed = self.internals.get_nowait()
                            self.log_info(f"Removed: {removed}")

                return

        self.log_info(f"[SYNC/{mode}] no match")
