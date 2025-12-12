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


def load_config():
    # base
    with open("config/base.yaml", "r") as f:
        base = yaml.safe_load(f)

    # setting
    with open("config/setting.yaml", "r") as f:
        setting = yaml.safe_load(f)

    merged1 = always_merger.merge(base, setting)

    # profile
    profile_id = merged1["id"]
    with open(f"config/profiles/{profile_id}.yaml", "r") as f:
        profile = yaml.safe_load(f)

    # test
    test_config_file_path = "config/profiles/test.yaml"
    if merged1["test_mode"]:
        with open("config/profiles/test.yaml", "r") as f:
            test = yaml.safe_load(f)
        profile = always_merger.merge(profile, test)
    
    return always_merger.merge(merged1, profile)

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