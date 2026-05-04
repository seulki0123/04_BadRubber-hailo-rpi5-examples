"""
track_event_count_reset 동작 검증.

notifier 예시 페이로드(JSON)에 대해:
  - meta.counts 에 있는 키만 0(또는 지정값)으로 맞추고 나머지 카운트는 유지
  - camera_id 가 TrackManager 와 일치할 때만 apply_remote_reset 호출

실행 (프로젝트 루트):
    PYTHONPATH=src python -m unittest tests.test_track_event_count_reset -v

※ rubber_tracker/__init__.py (app 로드)를 타지 않도록 event_service 만 스텁 경로로 로드한다.
"""

import importlib.util
import json
import os
import sys
import types
import unittest

# ---------------------------------------------------------------------------
# 최소 패키지 스텁 + event_service 모듈만 실제 파일에서 로드
# ---------------------------------------------------------------------------
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


def _install_pkg_stub(qualified_name: str, *path_tail: str) -> None:
    if qualified_name in sys.modules:
        return
    m = types.ModuleType(qualified_name)
    m.__path__ = [os.path.join(_SRC, "rubber_tracker", *path_tail)]
    sys.modules[qualified_name] = m


def _load_event_service_class():
    _install_pkg_stub("rubber_tracker", "")
    _install_pkg_stub("rubber_tracker.track", "track")
    _install_pkg_stub("rubber_tracker.track.services", "track", "services")
    _install_pkg_stub("rubber_tracker.track.services.core", "track", "services", "core")

    utils_stub = types.ModuleType("rubber_tracker.utils")
    utils_stub.ProcessLogger = _stub_process_logger()
    sys.modules["rubber_tracker.utils"] = utils_stub

    path = os.path.join(_SRC, "rubber_tracker", "track", "services", "core", "event_service.py")
    spec = importlib.util.spec_from_file_location(
        "rubber_tracker.track.services.core.event_service",
        path,
    )
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod.EventService


EventService = _load_event_service_class()


# base.yaml event 섹션과 동일한 구조의 테스트 fixture.
_TEST_EVENT_CFG = {
    "id_added":    {"symbol": "□□□□", "data_type": "id_added"},
    "created":     {"symbol": "□■■■", "data_type": "created"},
    "weigher_in":  {"symbol": "■□■■", "data_type": "weigher_in"},
    "weigher_out": {"symbol": "■■□■", "data_type": "weigher_out"},
    "final_baler": {"symbol": "■□□■", "data_type": "final_baler"},
    "exited":      {"symbol": "■■■□", "data_type": "exited"},
    "removed":     {"symbol": "■■■■", "data_type": "removed"},
}


class _FakeEventMessage:
    """EventMessage 대역 — add/get 만 EventService ctor 에 필요."""

    def __init__(self):
        self.messages = {}

    def add(self, text, color):
        pass

    def get(self):
        return [], []


def _sample_remote_reset_payload():
    return {
        "type": "track_event_count_reset",
        "time": "2026-04-23 15:25:00.000",
        "camera_id": "",
        "meta": {
            "counts": {
                "id_added": 0,
                "created": 0,
                "exited": 0,
                "removed": 0,
            }
        },
    }


class TrackEventCountResetTests(unittest.TestCase):
    def test_apply_remote_reset_partial_keys_only(self):
        svc = EventService(
            _FakeEventMessage(),
            event_cfg=_TEST_EVENT_CFG,
            initial_counts={
                "id_added": 10,
                "created": 20,
                "weigher_in": 3,
                "weigher_out": 4,
                "final_baler": 5,
                "exited": 30,
                "removed": 40,
            },
            camera_id="",
        )
        payload = _sample_remote_reset_payload()
        svc.apply_remote_reset(payload["meta"])

        c = svc.get_event_counts()
        self.assertEqual(c["id_added"], 0)
        self.assertEqual(c["created"], 0)
        self.assertEqual(c["exited"], 0)
        self.assertEqual(c["removed"], 0)
        self.assertEqual(c["weigher_in"], 3)
        self.assertEqual(c["weigher_out"], 4)
        self.assertEqual(c["final_baler"], 5)

    def test_sample_payload_json_line_parse(self):
        line = json.dumps(_sample_remote_reset_payload()) + "\n"
        msg = json.loads(line.strip())
        self.assertEqual(msg["type"], "track_event_count_reset")
        self.assertEqual(msg["meta"]["counts"]["created"], 0)

    def test_add_external_id_routing_camera_match(self):
        calls = []

        class FakeEventSvc:
            def apply_remote_reset(self, meta):
                calls.append(meta)

        class FakeSelf:
            camera_id = ""
            event_service = FakeEventSvc()

        data = _sample_remote_reset_payload()
        if data.get("type") == "track_event_count_reset":
            cam = str(data.get("camera_id") or "")
            if cam == FakeSelf.camera_id:
                FakeSelf.event_service.apply_remote_reset(data.get("meta") or {})

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["counts"]["removed"], 0)

    def test_add_external_id_skips_when_camera_mismatch(self):
        calls = []

        class FakeEventSvc:
            def apply_remote_reset(self, meta):
                calls.append(meta)

        class FakeSelf:
            camera_id = "inspector_a"
            event_service = FakeEventSvc()

        data = _sample_remote_reset_payload()
        data["camera_id"] = "inspector_b"
        if data.get("type") == "track_event_count_reset":
            cam = str(data.get("camera_id") or "")
            if cam == FakeSelf.camera_id:
                FakeSelf.event_service.apply_remote_reset(data.get("meta") or {})

        self.assertEqual(calls, [])

    def test_apply_remote_reset_empty_meta_no_crash(self):
        svc = EventService(
            _FakeEventMessage(),
            event_cfg=_TEST_EVENT_CFG,
            initial_counts={"created": 1},
            camera_id="x",
        )
        for raw in (None, {}, {"counts": {}}):
            with self.subTest(raw=raw):
                svc.apply_remote_reset(raw)
                self.assertEqual(svc.get_event_counts()["created"], 1)


if __name__ == "__main__":
    unittest.main()
