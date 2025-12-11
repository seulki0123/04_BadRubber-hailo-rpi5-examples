import queue
import threading
from rubber_tracker.utils import ModuleLogger


class BaseSyncModel(ModuleLogger):
    def __init__(self, name, max_queue_size, valid_queue_size, tolerance):
        super().__init__(self.__class__.__name__ + "_" + name, highlight=True)

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
        data_id, _ = item

        with lock:
            # check duplicate id
            for existing_id, _ in list(q.queue):
                if existing_id == data_id:
                    self.log_warning(f"Duplicate data_id detected: {data_id}, ignoring item")
                    return False

            # check queue full
            if q.full():
                self.log_warning("Queue full, ignoring item")
                return False

            # insert
            try:
                q.put_nowait(item)
                return True
            except queue.Full:
                return False

    def add_external(self, data_id, external):
        added = self._safe_put(self.externals, self._external_lock, (data_id, external))
        if added:
            self.log_info(f"External ID '{data_id}, {external}' added to externals")

    def add_internal(self, data_id, internal):
        added = self._safe_put(self.internals, self._internal_lock, (data_id, internal))
        if added:
            self.log_info(f"Internal ID '{data_id}, {internal}' added to internals")

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
            return None
        
        # raw queue
        externals_raw = list(self.externals.queue)   # list of (id, value)
        internals_raw = list(self.internals.queue)
        self.log_info(f"Externals raw: {externals_raw}")
        self.log_info(f"Internals raw: {internals_raw}")

        # dict 변환 (같은 id가 여러 개 들어오는 경우는 마지막만 사용)
        external_dict = {data_id: value for data_id, value in externals_raw}
        internal_dict = {data_id: value for data_id, value in internals_raw}

        # id 기반 intersection
        ext_ids = set(external_dict.keys())
        int_ids = set(internal_dict.keys())
        inter_ids = sorted(ext_ids & int_ids)

        # 누락된 id log
        missing_in_internal = ext_ids - int_ids
        missing_in_external = int_ids - ext_ids

        for mid in missing_in_internal:
            self.log_warning(f"ID {mid} exists in external but not in internal. Ignored.")
            self.log_info(f"Missing in internal: {missing_in_internal}")

        for mid in missing_in_external:
            self.log_warning(f"ID {mid} exists in internal but not in external. Ignored.")
            self.log_info(f"Missing in external: {missing_in_external}")

        # 정렬된 pair 리스트
        matched_externals = [external_dict[id] for id in inter_ids]
        matched_internals = [internal_dict[id] for id in inter_ids]
        
        self.log_info(f"Matched externals: {matched_externals}")
        self.log_info(f"Matched internals: {matched_internals}")

        # 패턴 생성
        if mode == "diff":
            ext_pattern = [
                (matched_externals[i] - matched_externals[i - 1]).total_seconds()
                for i in range(1, len(matched_externals))
            ]
            int_pattern = [
                (matched_internals[i] - matched_internals[i - 1]).total_seconds()
                for i in range(1, len(matched_internals))
            ]
        else:
            ext_pattern = matched_externals
            int_pattern = matched_internals

        self.log_info(f"Ext pattern: {ext_pattern}")
        self.log_info(f"Int pattern: {int_pattern}")

        # 유효 id pair가 부족
        if len(inter_ids) < self.valid_queue_size:
            return None
        
        # 패턴 비교 길이
        L_ext = len(ext_pattern)
        L_int = len(int_pattern)
        max_len = min(L_ext, L_int)

        if len(ext_pattern) < 0 or len(int_pattern) < 0:
            return None

        # suffix vs prefix matching
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
                    f"[SYNC/{mode}] matched_len={matched_len}, offset={offset}, ids={inter_ids}"
                )

                if offset >= 0:
                    self.log_info(f"[SYNC] sync succeeded (offset={offset}) → resetting queues")
                    self.reset_all()

                return offset

        self.log_info(f"[SYNC/{mode}] no match (ids={inter_ids})")

        if self.externals.full() or self.internals.full():
            self.log_warning("[SYNC] Queue full but no match → resetting queues")
            self.reset_all()
            
        return -1