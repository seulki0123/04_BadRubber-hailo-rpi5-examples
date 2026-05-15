from collections import deque

import numpy as np

from rubber_tracker.utils import ProcessLogger


class ValidTimeAdjuster(ProcessLogger):
    """
    sync 성공 시 매칭된 (external_time, internal_time) 쌍으로
    ExternalIdValidationService 의 min/max_create_seconds 를 유동적으로 조정한다.

    zone 별 설정(valid_time.<zone>.dynamic):
        enabled            : bool  — 유동 조정 활성화 여부
        margin_seconds     : float — 백분위 기준선에 더하고 빼는 오차 범위(초)
        min_sample_count   : int   — 이 개수 이상 쌓이면 임계값 계산 시작
        max_sample_count   : int   — 최근 Δ(초) 버퍼 상한(rolling); 오래된 값은 드롭
    """

    def __init__(self, validator, config: dict):
        super().__init__(self.__class__.__name__)
        self.validator = validator

        # zone 별 dynamic 설정 추출 ("dynamic" 키가 있는 zone 만 수집)
        self._zone_cfgs: dict[str, dict] = {
            zone: zone_cfg["dynamic"]
            for zone, zone_cfg in config.items()
            if isinstance(zone_cfg, dict) and "dynamic" in zone_cfg
        }

        self._buffers: dict[str, deque] = {}

    def on_match(self, zone: str, matched_pairs: list[tuple]):
        """
        SyncManager 의 time_match_callback 으로 등록된다.

        Args:
            zone          : sync zone 이름 (예: "branch_in", "join_in_a")
            matched_pairs : [(ext_datetime, int_datetime), ...] sync 성공 시의 매칭 쌍
        """
        dyn = self._zone_cfgs.get(zone, {})
        if not dyn.get("enabled", False) or not matched_pairs:
            return

        margin = float(dyn["margin_seconds"])
        min_samples = int(dyn["min_sample_count"])
        max_samples = int(dyn["max_sample_count"])

        # log matched pairs
        pair_parts = []
        for ext, int_ in matched_pairs:
            try:
                d = (int_ - ext).total_seconds()
                pair_parts.append(f"ext={ext!s} | int={int_!s} | Δ={d:.3f}s")
            except Exception:
                pair_parts.append(f"ext={ext!s} | int={int_!s} | Δ=calculation failed")
        self.log_info(
            f"[DynValidTime] zone '{zone}': sync matched_pairs ({len(matched_pairs)} pairs): "
            + ", ".join(pair_parts)
        )

        # buffer: maxlen = max_samples (rolling)
        buf = self._buffers.get(zone)
        if buf is None or buf.maxlen != max_samples:
            existing = list(buf) if buf else []
            buf = deque(existing[-max_samples:], maxlen=max_samples)
            self._buffers[zone] = buf

        # buffer append
        for ext_time, int_time in matched_pairs:
            try:
                dt = (int_time - ext_time).total_seconds()
                buf.append(dt)
            except Exception as e:
                self.log_warning(f"[DynValidTime] zone '{zone}': dt calculation failed — {e}")

        buf_snapshot = [round(x, 4) for x in buf]
        if len(buf) < min_samples:
            self.log_info(
                f"[DynValidTime] zone '{zone}': "
                f"insufficient samples for threshold update "
                f"({len(buf)}/{min_samples}, cap={max_samples}, rolling), "
                f"collecting more samples... buf={buf_snapshot}"
            )
            return

        # robust range: 10th / 90th percentile + margin
        arr = np.asarray(buf, dtype=float)
        p10 = float(np.percentile(arr, 10))
        p90 = float(np.percentile(arr, 90))

        min_dt = p10 - margin
        max_dt = p90 + margin

        self.log_info(
            f"[DynValidTime] zone '{zone}': "
            f"p10={p10:.2f}s, p90={p90:.2f}s, "
            f"min={min_dt:.2f}s, max={max_dt:.2f}s "
            f"(n={len(buf)}, cap={max_samples}, start≥{min_samples}, margin=±{margin}s, "
            f"raw_range=[{float(min(buf)):.2f}, {float(max(buf)):.2f}]s), "
            f"buf={buf_snapshot}"
        )

        self.validator.update_threshold(zone, min_dt, max_dt)
