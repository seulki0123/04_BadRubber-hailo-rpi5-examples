import glob

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