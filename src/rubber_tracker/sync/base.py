import queue
import threading
from collections import OrderedDict

from rubber_tracker.utils import ProcessLogger


class BaseSyncModel(ProcessLogger):
    def __init__(
        self,
        name,
        max_queue_size,
        valid_queue_size,
        tolerance,
        mismatch=0,
        stale_external_suppress_max=None,
    ):
        super().__init__(self.__class__.__name__ + "_" + name)

        self.max_queue_size = max_queue_size
        self.valid_queue_size = valid_queue_size
        self.tolerance = tolerance
        self.mismatch = mismatch

        # reset 직전 External에만 있던 ID: 큐 비운 뒤 늦게 Internal로 오면 무시(큐 증폭 방지).
        # 0이면 비활성, None이면 max_queue_size 사용.
        if stale_external_suppress_max is None:
            stale_external_suppress_max = max_queue_size * 3
        self._suppress_max = stale_external_suppress_max
        self._suppress_ordered = OrderedDict()
        self._suppress_lock = threading.Lock()

        self.externals = queue.Queue(maxsize=max_queue_size + 1)  # +1: use queue.full() as overflow signal for sync
        self.internals = queue.Queue(maxsize=max_queue_size + 1)

        self._external_lock = threading.Lock()
        self._internal_lock = threading.Lock()

        self._last_matched_pairs: list[tuple] = []  # [(ext_val, int_val), ...] from last successful sync

    # Queue Reset
    def _reset_queue(self, q: queue.Queue, lock: threading.Lock):
        with lock, q.mutex:
            q.queue.clear()
            q.unfinished_tasks = 0
            q.all_tasks_done.notify_all()
            self.log_info("Queue reset")

    def _snapshot_external_internal_ids(self):
        with self._external_lock, self.externals.mutex:
            ext_ids = {data_id for data_id, _ in self.externals.queue}
        with self._internal_lock, self.internals.mutex:
            int_ids = {data_id for data_id, _ in self.internals.queue}
        return ext_ids, int_ids

    def _remember_stale_external_only_ids(self, stale_ids):
        if self._suppress_max <= 0 or not stale_ids:
            return
        with self._suppress_lock:
            for data_id in sorted(stale_ids):
                self._suppress_ordered.pop(data_id, None)
                self._suppress_ordered[data_id] = None
                while len(self._suppress_ordered) > self._suppress_max:
                    evicted_id, _ = self._suppress_ordered.popitem(last=False)
                    self.log_info(f"[SUPPRESS] evicted oldest id '{evicted_id}' (cap={self._suppress_max})")
            self.log_info(
                f"[SUPPRESS] recorded {len(stale_ids)} stale external-only id(s): {sorted(stale_ids)} | "
                f"suppress list now ({len(self._suppress_ordered)}/{self._suppress_max}): "
                f"{list(self._suppress_ordered.keys())}"
            )

    def _consume_suppressed_internal(self, data_id) -> bool:
        """내부로 들어오는 stale external id면 True(put 하지 않음)."""
        if self._suppress_max <= 0:
            return False
        with self._suppress_lock:
            if data_id not in self._suppress_ordered:
                return False
            del self._suppress_ordered[data_id]
            self.log_info(
                f"[SUPPRESS] ignored internal ID {data_id} (matched pre-reset external-only backlog)"
            )
            return True

    def reset_all(self, remember_stale: bool = True):
        if remember_stale:
            ext_ids, int_ids = self._snapshot_external_internal_ids()
            stale_only = ext_ids - int_ids
            self._remember_stale_external_only_ids(stale_only)
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

    def has_external_id(self, data_id) -> bool:
        with self._external_lock:
            return any(eid == data_id for eid, _ in self.externals.queue)

    def add_external(self, data_id, external):
        added = self._safe_put(self.externals, self._external_lock, (data_id, external))
        if added:
            self.log_info(f"External ID '{data_id}, {external}' added to externals")

    def add_internal(self, data_id, internal) -> bool:
        if self._consume_suppressed_internal(data_id):
            return False
        if not self.has_external_id(data_id):
            self.log_warning(
                f"Internal ID '{data_id}' has no matching external. Ignoring."
            )
            return False
        added = self._safe_put(self.internals, self._internal_lock, (data_id, internal))
        if added:
            self.log_info(f"Internal ID '{data_id}, {internal}' added to internals")
        return added

    def _is_queue_overflow_state(self) -> bool:
        with self._external_lock, self._internal_lock:
            return self.externals.full() or self.internals.full()

    # Sync helpers
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

    def _prefix_match_strict_mismatch(self, ext_arr, int_arr, max_mismatch):
        mismatch = 0
        matched = 0

        for a, b in zip(ext_arr, int_arr):
            if a != b:
                mismatch += 1
                if mismatch > max_mismatch:  
                    break
            matched += 1

        return matched

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

    # Main Sync Logic
    def sync(self, mode="diff"):
        if not mode in ["diff", "strict"]:
            self.log_error(f"Invalid mode: {mode}")
            return None

        # raw queue
        with self._external_lock:
            externals_raw = list(self.externals.queue)
        with self._internal_lock:
            internals_raw = list(self.internals.queue)
        self.log_info(f"Externals raw: {externals_raw}")
        self.log_info(f"Internals raw: {internals_raw}")

        # dict 변환 (같은 id가 여러 개 들어오면 마지막만 사용)
        external_dict = {data_id: value for data_id, value in externals_raw}
        internal_dict = {data_id: value for data_id, value in internals_raw}

        # id 기반 intersection
        ext_ids = set(external_dict.keys())
        int_ids = set(internal_dict.keys())
        inter_ids = sorted(ext_ids & int_ids)

        # 누락 ID 로그
        missing_in_internal = ext_ids - int_ids
        missing_in_external = int_ids - ext_ids

        for mid in missing_in_internal:
            self.log_warning(f"ID {mid} exists in external but not in internal. Ignored.")
            self.log_info(f"Missing in internal: {missing_in_internal}")

        for mid in missing_in_external:
            self.log_warning(f"ID {mid} exists in internal but not in external. Ignored.")
            self.log_info(f"Missing in external: {missing_in_external}")

        # 정렬된 lists
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
            # strict(raw) 모드
            ext_pattern = matched_externals
            int_pattern = matched_internals

        self.log_info(f"Ext pattern: {ext_pattern}")
        self.log_info(f"Int pattern: {int_pattern}")

        if self._is_queue_overflow_state():
            self.log_warning("[SYNC] queues are full before sync → reset")
            self.reset_all(remember_stale=False)
            return -1

        # 유효 ID 개수 부족
        if len(inter_ids) < self.valid_queue_size:
            return None
        
        # 패턴 길이
        L_ext = len(ext_pattern)
        L_int = len(int_pattern)
        max_len = min(L_ext, L_int)

        if L_ext < self.valid_queue_size or L_int < self.valid_queue_size:
            return None

        # suffix vs prefix matching
        for match_len in range(max_len, self.valid_queue_size - 1, -1):
            ext_sub = ext_pattern[:match_len]
            int_sub = int_pattern[-match_len:]

            # strict(raw) 모드 + mismatch 옵션
            if mode == "strict":
                if  self.mismatch > 0:
                    matched_len = self._prefix_match_strict_mismatch(ext_sub, int_sub, self.mismatch)
                else:
                    matched_len = self._prefix_match_strict(ext_sub, int_sub)
            else:
                # diff mode
                matched_len = self._prefix_match_diff(ext_sub, int_sub, self.tolerance)

            if matched_len >= self.valid_queue_size:
                offset = L_int - matched_len
                self.log_info(
                    f"[SYNC/{mode}] matched_len={matched_len}, offset={offset}, ids={inter_ids}"
                )
                
                if offset == 0:
                    self._last_matched_pairs = list(zip(matched_externals, matched_internals))

                if offset >= 0:
                    self.log_info(f"[SYNC] sync succeeded (offset={offset}) → resetting queues")
                    self.reset_all(remember_stale=False)

                return offset

        self.log_info(f"[SYNC/{mode}] no match (ids={inter_ids})")
        return None