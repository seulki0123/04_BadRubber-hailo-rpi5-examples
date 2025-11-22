import glob
import random
import colorsys

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