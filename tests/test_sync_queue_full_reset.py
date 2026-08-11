import importlib.util
import os
import sys
import types
import unittest
from datetime import datetime, timedelta


_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC = os.path.join(_PROJECT_ROOT, "src")


def _stub_process_logger():
    class ProcessLogger:
        def __init__(self, _name=None):
            pass

        def log_warning(self, *_, **__):
            pass

        def log_info(self, *_, **__):
            pass

        def log_error(self, *_, **__):
            pass

    return ProcessLogger


def _load_base_sync_model():
    pkg = types.ModuleType("rubber_tracker")
    pkg.__path__ = [os.path.join(_SRC, "rubber_tracker")]
    sys.modules["rubber_tracker"] = pkg

    sync_pkg = types.ModuleType("rubber_tracker.sync")
    sync_pkg.__path__ = [os.path.join(_SRC, "rubber_tracker", "sync")]
    sys.modules["rubber_tracker.sync"] = sync_pkg

    utils_stub = types.ModuleType("rubber_tracker.utils")
    utils_stub.ProcessLogger = _stub_process_logger()
    sys.modules["rubber_tracker.utils"] = utils_stub

    path = os.path.join(_SRC, "rubber_tracker", "sync", "base.py")
    spec = importlib.util.spec_from_file_location("rubber_tracker.sync.base", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.BaseSyncModel


def _load_sync_manager():
    utils_stub = sys.modules["rubber_tracker.utils"]
    utils_stub.load_config = lambda _profile_id=None: {}

    path = os.path.join(_SRC, "rubber_tracker", "sync", "sync.py")
    spec = importlib.util.spec_from_file_location("rubber_tracker.sync.sync", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.SyncManager


def _load_external_id_service():
    path = os.path.join(
        _SRC,
        "rubber_tracker",
        "track",
        "services",
        "external",
        "id_service.py",
    )
    spec = importlib.util.spec_from_file_location("track_ids_cleared_id_service", path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    return mod.ExternalIdService


BaseSyncModel = _load_base_sync_model()
SyncManager = _load_sync_manager()
ExternalIdService = _load_external_id_service()


def _ids(q):
    with q.mutex:
        return [data_id for data_id, _ in q.queue]


class _ClearedIdsQueueManager:
    def __init__(self, cleared):
        self.cleared = cleared
        self.requested_zones = None

    def clear_external_ids(self, zones):
        self.requested_zones = zones
        return self.cleared


class TrackIdsClearedTest(unittest.TestCase):
    @staticmethod
    def _service(cleared):
        queue_manager = _ClearedIdsQueueManager(cleared)
        service = ExternalIdService(queue_manager, None, None, {}, None, None)
        return service, queue_manager

    def test_clear_notifies_each_nonempty_zone(self):
        cleared = {
            "join_in_a": ["A001"],
            "join_in_b": ["B001", "B002"],
        }
        service, queue_manager = self._service(cleared)
        sent = []
        service.set_notifier_send(sent.append)

        result = service.clear_ids_for_zones(["join_in_a", "join_in_b"])

        self.assertIs(result, cleared)
        self.assertEqual(queue_manager.requested_zones, ["join_in_a", "join_in_b"])
        self.assertEqual(
            [(payload["type"], payload["zone"], payload["ids"]) for payload in sent],
            [
                ("track_ids_cleared", "join_in_a", ["A001"]),
                ("track_ids_cleared", "join_in_b", ["B001", "B002"]),
            ],
        )
        self.assertTrue(all(payload.get("time") for payload in sent))

    def test_clear_with_no_ids_does_not_notify(self):
        service, _ = self._service({})
        sent = []
        service.set_notifier_send(sent.append)

        service.clear_ids_for_zones(["join_in_a"])

        self.assertEqual(sent, [])


class SyncQueueFullResetTest(unittest.TestCase):
    def test_remove_external_removes_only_matching_id(self):
        sync = BaseSyncModel(
            "test",
            max_queue_size=3,
            valid_queue_size=1,
            tolerance=0,
        )
        sync.add_external("a", 1)
        sync.add_external("b", 2)
        sync.add_external("c", 3)

        self.assertTrue(sync.remove_external("b"))
        self.assertEqual(_ids(sync.externals), ["a", "c"])
        self.assertFalse(sync.remove_external("missing"))
        self.assertEqual(_ids(sync.externals), ["a", "c"])

    def test_missing_internal_baler_removes_external_candidate(self):
        sync = BaseSyncModel(
            "test",
            max_queue_size=3,
            valid_queue_size=1,
            tolerance=0,
        )
        sync.add_external("drop", 1)
        sync.add_external("keep", 2)

        manager = SyncManager.__new__(SyncManager)
        manager.baler_sync = {"a": sync, "b": None}
        manager.baler_event = {
            "external": {"a": "id_added_branch_out_a", "b": None},
            "internal": {"a": "final_baler_house_in_a", "b": None},
        }
        manager._suspended = set()

        manager.add_internal_baler(
            {
                "id": "drop",
                "event": "final_baler_house_in_a",
                "final_baler": None,
            }
        )

        self.assertEqual(_ids(sync.externals), ["keep"])
        self.assertEqual(_ids(sync.internals), [])

    def test_add_external_preserves_datetime_values_for_time_sync(self):
        sync = BaseSyncModel(
            "test",
            max_queue_size=5,
            valid_queue_size=1,
            tolerance=0.1,
        )
        t0 = datetime(2026, 7, 8, 20, 16, 40, 486000)
        t1 = t0 + timedelta(seconds=10)

        sync.add_external("a", t0)
        sync.add_external("b", t1)
        self.assertTrue(sync.add_internal("a", t0))
        self.assertTrue(sync.add_internal("b", t1))

        self.assertEqual(sync.sync(mode="diff"), 0)

    def test_add_external_normalizes_numeric_strings_for_baler_sync(self):
        sync = BaseSyncModel(
            "test",
            max_queue_size=2,
            valid_queue_size=1,
            tolerance=0,
        )

        sync.add_external("a", "11")

        with sync._external_lock, sync.externals.mutex:
            self.assertEqual(list(sync.externals.queue), [("a", 11)])

    def test_add_external_resets_sync_queues_when_queue_is_full(self):
        sync = BaseSyncModel(
            "test",
            max_queue_size=2,
            valid_queue_size=1,
            tolerance=0,
        )

        sync.add_external("a", 1)
        sync.add_external("b", 2)
        self.assertEqual(sync.add_external("c", 3), -1)
        sync.add_external("d", 4)

        self.assertEqual(_ids(sync.externals), ["d"])
        self.assertEqual(_ids(sync.internals), [])
        self.assertTrue(sync.add_internal("d", 4))

    def test_emergency_full_queue_is_verified_before_reset(self):
        sync = BaseSyncModel(
            "test",
            max_queue_size=3,
            valid_queue_size=2,
            tolerance=0,
        )
        t0 = datetime(2026, 7, 8, 20, 0, 0)

        with sync._external_lock, sync.externals.mutex:
            for index in range(4):
                item = (str(index), t0 + timedelta(seconds=index * 10))
                sync.externals.queue.append(item)
                sync.externals.unfinished_tasks += 1

        with sync._internal_lock, sync.internals.mutex:
            for index in range(4):
                item = (str(index), t0 + timedelta(seconds=index * 10))
                sync.internals.queue.append(item)
                sync.internals.unfinished_tasks += 1

        self.assertIsNone(sync.add_internal("x", t0 + timedelta(seconds=40)))
        self.assertEqual(_ids(sync.externals), ["0", "1", "2", "3"])
        self.assertEqual(_ids(sync.internals), ["0", "1", "2", "3"])

        self.assertEqual(sync.sync(mode="diff"), 0)
        self.assertEqual(_ids(sync.externals), [])
        self.assertEqual(_ids(sync.internals), [])

    def test_matching_data_is_verified_before_queue_limit_reset(self):
        sync = BaseSyncModel(
            "test",
            max_queue_size=3,
            valid_queue_size=2,
            tolerance=0.1,
        )
        t0 = datetime(2026, 7, 8, 20, 0, 0)

        results = []
        for index, seconds in enumerate((0, 10, 20)):
            data_id = str(index)
            value = t0 + timedelta(seconds=seconds)
            sync.add_external(data_id, value)
            self.assertTrue(sync.add_internal(data_id, value))
            results.append(sync.sync(mode="diff"))

        self.assertEqual(results, [None, None, 0])
        self.assertEqual(_ids(sync.externals), [])
        self.assertEqual(_ids(sync.internals), [])

    def test_pattern_mismatch_at_queue_limit_requests_reset(self):
        sync = BaseSyncModel(
            "test",
            max_queue_size=3,
            valid_queue_size=2,
            tolerance=0.1,
        )
        t0 = datetime(2026, 7, 8, 20, 0, 0)

        external_seconds = (0, 10, 20)
        internal_seconds = (0, 30, 60)
        results = []
        for index, (ext_seconds, int_seconds) in enumerate(
            zip(external_seconds, internal_seconds)
        ):
            data_id = str(index)
            sync.add_external(data_id, t0 + timedelta(seconds=ext_seconds))
            self.assertTrue(
                sync.add_internal(data_id, t0 + timedelta(seconds=int_seconds))
            )
            results.append(sync.sync(mode="diff"))

        self.assertEqual(results, [None, None, -1])
        self.assertEqual(_ids(sync.externals), [])
        self.assertEqual(_ids(sync.internals), [])

    def test_pattern_mismatch_below_queue_limit_keeps_collecting(self):
        sync = BaseSyncModel(
            "test",
            max_queue_size=4,
            valid_queue_size=2,
            tolerance=0.1,
        )
        t0 = datetime(2026, 7, 8, 20, 0, 0)

        results = []
        for index, (ext_seconds, int_seconds) in enumerate(((0, 0), (10, 30), (20, 60))):
            data_id = str(index)
            sync.add_external(data_id, t0 + timedelta(seconds=ext_seconds))
            self.assertTrue(
                sync.add_internal(data_id, t0 + timedelta(seconds=int_seconds))
            )
            results.append(sync.sync(mode="diff"))

        self.assertEqual(results, [None, None, None])
        self.assertEqual(_ids(sync.externals), ["0", "1", "2"])
        self.assertEqual(_ids(sync.internals), ["0", "1", "2"])


if __name__ == "__main__":
    unittest.main()
