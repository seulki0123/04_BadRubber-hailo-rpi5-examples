"""
pytest 전역 설정.

macOS/Windows 등 GStreamer(gi)가 설치되지 않은 개발 환경에서도
event_image_saver 모듈을 단독 테스트할 수 있도록, rubber_tracker가 로드되기
전에 gi.repository와 hailo_apps_infra 등 외부 의존성을 stub 처리한다.

이 파일은 테스트 전용이며, 운영 코드에는 영향이 전혀 없다.
"""
import os
import sys
import types

# ------------------------------------------------------------
# 프로젝트 경로 설정
# ------------------------------------------------------------
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
_SRC_PATH = os.path.join(_PROJECT_ROOT, "src")
if _SRC_PATH not in sys.path:
    sys.path.insert(0, _SRC_PATH)
os.chdir(_PROJECT_ROOT)


# ------------------------------------------------------------
# 만능 stub 모듈 — 어떤 attribute 요청에도 또다른 stub를 반환
# ------------------------------------------------------------
class _StubModule(types.ModuleType):
    """요청되는 모든 속성을 무해한 기본값으로 반환하는 모듈 stub."""
    def __init__(self, name: str):
        super().__init__(name)
        self.__path__ = []          # 서브모듈 import 허용 (namespace package 흉내)
        self._cache: dict = {}

    def __getattr__(self, item: str):
        if item in self._cache:
            return self._cache[item]

        # 서브모듈이 요청되는 경우 → 하위 stub 생성
        sub_name = f"{self.__name__}.{item}"
        sub = sys.modules.get(sub_name)
        if sub is None:
            sub = _StubModule(sub_name)
            sys.modules[sub_name] = sub

        # attribute로도 사용될 수 있으므로 noop callable + sub module 혼용
        # → 함수처럼 호출되면 None 반환하고, 속성 접근 시 StubModule
        class _CallableStub:
            def __init__(self, mod): self._mod = mod
            def __call__(self, *a, **kw): return None
            def __getattr__(self, k): return getattr(self._mod, k)
            def __repr__(self): return f"<StubCallable {sub_name}>"

        # 클래스로 쓰이는 케이스(상속 등)가 많으니 type도 동시에 지원
        # 핵심 패턴: class Foo(GStreamerDetectionApp): ... 가 동작하도록 type을 반환
        stub_type = type(item, (object,), {
            "__init__": lambda self, *a, **kw: None,
            "__call__": lambda self, *a, **kw: None,
        })
        self._cache[item] = stub_type
        return stub_type


def _install_stub_package(name: str) -> _StubModule:
    if name in sys.modules and isinstance(sys.modules[name], _StubModule):
        return sys.modules[name]
    mod = _StubModule(name)
    sys.modules[name] = mod
    return mod


# ------------------------------------------------------------
# 외부 의존성 stub
# ------------------------------------------------------------
# gi — 특수 처리 (require_version 함수 필요)
if "gi" not in sys.modules:
    _gi = types.ModuleType("gi")
    _gi.require_version = lambda *a, **kw: None
    sys.modules["gi"] = _gi

# gi.repository — 특수: Gst 및 GLib 필요
if "gi.repository" not in sys.modules:
    _gi_repo = types.ModuleType("gi.repository")

    class _StubGst:
        Buffer = type("Buffer", (), {})
        Caps = type("Caps", (), {"from_string": staticmethod(lambda s: None)})
        Format = type("Format", (), {"TIME": 3})
        FlowReturn = type("FlowReturn", (), {"OK": 0})
        PadProbeReturn = type("PadProbeReturn", (), {"OK": 0})
        SECOND = 1_000_000_000

        @staticmethod
        def util_uint64_scale_int(a, b, c):
            return (a * b) // max(c, 1)

    _gi_repo.Gst = _StubGst
    _gi_repo.GLib = types.SimpleNamespace(MainLoop=lambda: None)
    sys.modules["gi.repository"] = _gi_repo
    # gi.repository 를 gi의 속성으로도 등록
    sys.modules["gi"].repository = _gi_repo


# hailo_apps_infra 및 서브모듈들 — 만능 stub
_install_stub_package("hailo_apps_infra")
_install_stub_package("hailo_apps_infra.detection_pipeline")
_install_stub_package("hailo_apps_infra.gstreamer_app")
_install_stub_package("hailo_apps_infra.hailo_rpi_common")
_install_stub_package("hailo_apps_infra.gstreamer_helper_pipelines")

# hailo (Hailo ROI API) — 만능 stub
_install_stub_package("hailo")


# ultralytics YOLO — callable 필요 (YOLO(...) 형태)
if "ultralytics" not in sys.modules:
    _ultra = types.ModuleType("ultralytics")
    _ultra.YOLO = lambda *a, **kw: None
    sys.modules["ultralytics"] = _ultra


# deepmerge — utils/utils.py 의 load_config 에서 사용
if "deepmerge" not in sys.modules:
    try:
        import deepmerge  # noqa: F401
    except ImportError:
        _dm = types.ModuleType("deepmerge")

        class _AlwaysMerger:
            @staticmethod
            def merge(base, override):
                if not isinstance(base, dict) or not isinstance(override, dict):
                    return override
                for k, v in override.items():
                    if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                        _AlwaysMerger.merge(base[k], v)
                    else:
                        base[k] = v
                return base

        _dm.always_merger = _AlwaysMerger()
        sys.modules["deepmerge"] = _dm


# psutil — monitoring 에서 사용
if "psutil" not in sys.modules:
    try:
        import psutil  # noqa: F401
    except ImportError:
        _ps = types.ModuleType("psutil")
        _ps.cpu_percent = lambda **kw: 0.0
        _ps.virtual_memory = lambda: types.SimpleNamespace(
            used=0, total=1, percent=0.0)
        _ps.disk_usage = lambda p: types.SimpleNamespace(
            used=0, total=1, free=1, percent=0.0)
        sys.modules["psutil"] = _ps
