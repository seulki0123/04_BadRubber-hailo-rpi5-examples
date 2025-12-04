class Gate:
    """Single zone with mask and hit detection."""

    def __init__(self, name, mask):
        self.name = name
        self.mask = mask  # mask is already loaded & resized (numpy array)

    def bbox_hit_zone(self, bbox):
        if self.mask is None:
            return None

        x1, y1, x2, y2 = map(int, bbox)
        h, w = self.mask.shape

        x1 = max(0, min(x1, w - 1))
        x2 = max(0, min(x2, w))
        y1 = max(0, min(y1, h - 1))
        y2 = max(0, min(y2, h))

        if x2 <= x1 or y2 <= y1:
            return None

        roi = self.mask[y1:y2, x1:x2]
        return self.name if roi.any() else None

    def point_in_zone(self, center):
        x, y = map(int, center)
        h, w = self.mask.shape

        if not (0 <= x < w and 0 <= y < h):
            return None

        return self.name if self.mask[y, x] else None