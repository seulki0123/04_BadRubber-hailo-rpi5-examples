import yaml

def load_config(path="configs/base.yaml"):
    cfg = {}
    raw = yaml.safe_load(open(path))

    for inc in raw.get("include", []):
        cfg.update(load_config(inc))

    cfg.update({k: v for k, v in raw.items() if k != "include"})
    return cfg