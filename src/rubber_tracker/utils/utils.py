import copy
import glob
import random
import colorsys
import traceback
from functools import wraps

import yaml
from deepmerge import always_merger

def is_display_connected():
    """Check if any DRM status reports 'connected'."""
    paths = glob.glob("/sys/class/drm/*/status")

    for p in paths:
        try:
            with open(p, "r") as f:
                status = f.read().strip()
                if status == "connected":
                    print("***** Display is connected *****")
                    return True
        except:
            pass

    print("***** Display is disconnected *****")
    return False

def generate_color():
    h = random.random()            # 0~1
    s = random.uniform(0.6, 1.0)   # 채도: 너무 낮으면 회색 느낌 → 0.6 이상
    v = random.uniform(0.8, 1.0)   # 밝기: 너무 어두운 색 방지 → 0.8 이상

    r, g, b = colorsys.hsv_to_rgb(h, s, v)
    return (int(r*255), int(g*255), int(b*255))


# ============================================================
# Config loader
# ------------------------------------------------------------
# setting.yaml 의 `id` 가 단일 string 이면 기존 동작과 동일하게 base+setting+profile
# 을 머지해서 반환한다. `id` 가 리스트인 경우 (멀티 프로파일 모드):
#   - profile_id 명시: 해당 프로파일을 머지해서 반환 (per-profile 컴포넌트용).
#   - profile_id 미명시: 첫 프로파일을 머지해서 반환 (공용 컴포넌트용).
#       이때 모든 프로파일이 _SHARED_PROFILE_KEYS 값들을 동일하게 가져야 하며,
#       하나라도 다르면 RuntimeError 를 raise 해 부팅을 중단한다.
#
# 또한 결과 dict 에 다음 두 표준 키를 합성해 넣는다.
#   - _profile_ids:        설정의 id 를 항상 리스트로 정규화한 값
#   - _active_profile_id:  실제로 머지에 사용된 프로파일 id
#   - ipcamera.urls:       모든 프로파일의 ipcamera.url 을 모은 리스트
#                          (단일 프로파일이면 url / url1 / url2 까지 흡수)
# ============================================================

# 모든 프로파일에서 동일해야 하는 키들. NPU/Tracker/Buffer/공용 IPCamera 파라미터는
# 단일 GStreamer 파이프라인을 공유하므로 프로파일별로 다를 수 없다.
_SHARED_PROFILE_KEYS = [
    ("detect", "weight"),
    ("detect", "score_threshold"),
    ("ipcamera", "width"),
    ("ipcamera", "height"),
    ("ipcamera", "fps"),
    ("ipcamera", "format"),
    ("ipcamera", "thread_interval"),
    ("ipcamera", "blank"),
    ("ipcamera", "blocked"),
    ("tracker", "iou_threshold"),
    ("tracker", "old_threshold"),
    ("tracker", "scale_w"),
    ("tracker", "scale_h"),
    ("tracker", "age_threshold"),
    ("tracker", "area_threshold"),
    ("post_processor", "thread_interval"),
    ("post_processor", "containment_threshold"),
    ("detection_queue", "max_size"),
    ("detection_queue", "logging_interval"),
    ("detection_queue", "get_timeout"),
]

# 멀티 프로파일 공용 키 검증은 부팅당 1회만 수행
_SHARED_VALIDATED = False


def _load_yaml(path):
    with open(path, "r") as f:
        return yaml.safe_load(f) or {}


def _get_path(d, path):
    cur = d
    for k in path:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(k)
    return cur


def _normalize_ids(value):
    if value is None or value == "":
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        if not all(isinstance(x, str) and x for x in value):
            raise ValueError(f"setting.yaml 의 id 리스트는 비어있지 않은 문자열이어야 합니다: {value!r}")
        return list(value)
    raise ValueError(f"setting.yaml 의 id 는 string 또는 list[str] 이어야 합니다: {type(value).__name__}={value!r}")


def _profile_path(profile_id):
    return f"config/profiles/{profile_id}.yaml"


def _build_full_config(profile_id, *, base, setting, test_mode):
    """base + setting + profiles/{profile_id} (+ test if test_mode) 를 머지한다."""
    merged = always_merger.merge(copy.deepcopy(base), copy.deepcopy(setting))
    profile = _load_yaml(_profile_path(profile_id))
    if test_mode:
        test = _load_yaml("config/profiles/test.yaml")
        profile = always_merger.merge(profile, test)
    return always_merger.merge(merged, profile)


def _validate_shared_consistency(profile_ids, *, base, setting, test_mode):
    """모든 프로파일이 _SHARED_PROFILE_KEYS 값들을 동일하게 가졌는지 확인한다."""
    configs = [
        _build_full_config(pid, base=base, setting=setting, test_mode=test_mode)
        for pid in profile_ids
    ]

    mismatches = []
    for path in _SHARED_PROFILE_KEYS:
        values = [_get_path(c, path) for c in configs]
        # 모든 값이 동일한지 repr 기준으로 비교 (None 도 허용)
        if len({repr(v) for v in values}) > 1:
            mismatches.append((path, list(zip(profile_ids, values))))

    if not mismatches:
        return

    lines = [
        f"[load_config] 멀티 프로파일 공용 키 불일치 ({len(profile_ids)}개 프로파일)."
        " 아래 키들은 모든 프로파일에서 동일해야 합니다 (단일 NPU/카메라 파이프라인 공용):"
    ]
    for path, pairs in mismatches:
        key = ".".join(path)
        lines.append(f"  - {key}:")
        for pid, val in pairs:
            lines.append(f"      [{pid}] = {val!r}")
    raise RuntimeError("\n".join(lines))


def _compose_ipcamera_urls(final, profile_ids, *, base, setting, test_mode):
    """ipcamera.urls 표준 키를 합성한다.

    - 멀티 프로파일: 각 프로파일의 ipcamera.url 을 순서대로 모은다.
    - 단일 프로파일: url / url1 / url2 를 차례로 모아 중복 제거.
    """
    cam = final.setdefault("ipcamera", {})
    if cam.get("urls"):
        return  # 이미 명시적으로 지정돼 있으면 존중

    urls = []
    if len(profile_ids) > 1:
        # 멀티 프로파일: 각 프로파일이 자기 카메라 1대를 들고 있다고 가정.
        # url 우선, 없으면 url1 → url2 순서로 fallback.
        for pid in profile_ids:
            p_full = _build_full_config(pid, base=base, setting=setting, test_mode=test_mode)
            p_cam = p_full.get("ipcamera", {})
            u = p_cam.get("url") or p_cam.get("url1") or p_cam.get("url2")
            if u:
                urls.append(u)
    else:
        for key in ("url", "url1", "url2"):
            u = cam.get(key)
            if u:
                urls.append(u)
        urls = list(dict.fromkeys(urls))  # 중복 제거 (url == url1 케이스 등)

    cam["urls"] = urls


def load_config(profile_id=None):
    """프로파일 머지된 config 를 반환한다.

    Args:
        profile_id: 멀티 프로파일 모드에서 특정 프로파일을 명시할 때 사용.
                    None 이면 첫 프로파일이 사용된다 (공용 컴포넌트용).

    Raises:
        RuntimeError: 멀티 프로파일 모드에서 공용 키가 일치하지 않을 때.
    """
    base = _load_yaml("config/base.yaml")
    setting = _load_yaml("config/setting.yaml")

    base_setting = always_merger.merge(copy.deepcopy(base), copy.deepcopy(setting))
    profile_ids = _normalize_ids(base_setting.get("id"))
    test_mode = bool(base_setting.get("test_mode", False))

    if not profile_ids:
        raise RuntimeError("setting.yaml 의 'id' 가 비어 있습니다.")

    if profile_id is None:
        # 공용 컴포넌트가 부르는 경로. 멀티 프로파일이면 검증 후 첫 프로파일 사용.
        if len(profile_ids) > 1:
            global _SHARED_VALIDATED
            if not _SHARED_VALIDATED:
                _validate_shared_consistency(
                    profile_ids, base=base, setting=setting, test_mode=test_mode
                )
                _SHARED_VALIDATED = True
        chosen = profile_ids[0]
    else:
        if profile_id not in profile_ids:
            raise RuntimeError(
                f"profile_id '{profile_id}' 은 setting.yaml 의 id 목록에 없습니다: {profile_ids}"
            )
        chosen = profile_id

    final = _build_full_config(chosen, base=base, setting=setting, test_mode=test_mode)

    _compose_ipcamera_urls(final, profile_ids, base=base, setting=setting, test_mode=test_mode)

    final["_profile_ids"] = profile_ids
    final["_active_profile_id"] = chosen

    return final


def safe_call(func):
    @wraps(func)
    def wrapper(self, *args, **kwargs):
        try:
            return func(self, *args, **kwargs)
        except Exception:
            # self.logger 있으면 쓰고, 없으면 print
            if hasattr(self, 'logger'):
                self.logger.error(f"Error in '{func.__name__}' function : {traceback.format_exc()}")
            else:
                raise Exception(f"Error in '{func.__name__}' function : {traceback.format_exc()}")
            return None
    return wrapper
