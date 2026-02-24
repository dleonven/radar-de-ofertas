from __future__ import annotations

from dataclasses import dataclass
from statistics import median


SCORING_VERSION = "v1"
MIN_VISIBLE_DISCOUNT_FOR_REAL = 0.10
LIKELY_REAL_MIN_SCORE = 0.55


@dataclass
class ScoreInput:
    price_current: float
    price_list: float | None
    history_prices: list[float]
    history_list_prices: list[float]
    cross_store_prices: list[float]
    snapshot_count_recent: int


@dataclass
class ScoreResult:
    score: float
    label: str
    discount_pct: float | None
    hist_delta_pct: float | None
    cross_store_delta_pct: float | None
    anchor_anomaly_flag: bool
    rule_trace: dict[str, object]


def _clip(value: float, low: float, high: float) -> float:
    return max(low, min(value, high))


def evaluate_discount(inp: ScoreInput) -> ScoreResult:
    discount_pct = None
    if inp.price_list and inp.price_list > 0:
        discount_pct = (inp.price_list - inp.price_current) / inp.price_list

    hist_delta_pct = None
    if inp.history_prices:
        hist_med = median(inp.history_prices)
        if hist_med > 0:
            hist_delta_pct = (hist_med - inp.price_current) / hist_med

    cross_store_delta_pct = None
    if inp.cross_store_prices:
        cross_med = median(inp.cross_store_prices)
        if cross_med > 0:
            cross_store_delta_pct = (cross_med - inp.price_current) / cross_med

    anchor_spike_pct = 0.0
    if inp.price_list and inp.history_list_prices:
        list_med = median(inp.history_list_prices)
        if list_med > 0:
            anchor_spike_pct = (inp.price_list - list_med) / list_med

    r1 = (hist_delta_pct or 0.0) >= 0.15
    r2 = anchor_spike_pct <= 0.10
    r3 = (cross_store_delta_pct or 0.0) >= 0.05
    r4 = inp.snapshot_count_recent >= 2
    r5 = len(inp.history_prices) >= 10
    r6 = (discount_pct or 0.0) >= MIN_VISIBLE_DISCOUNT_FOR_REAL

    duration_score = 1.0 if r4 else 0.0
    data_quality_score = 1.0 if r5 else 0.4

    hist_component = _clip(hist_delta_pct or 0.0, 0.0, 0.5) / 0.5
    if cross_store_delta_pct is None:
        cross_component = 0.5  # neutral value when only one retailer is tracked
    else:
        # Small differences vs peers are treated as pricing noise.
        if -0.03 <= cross_store_delta_pct <= 0.03:
            cross_component = 0.5
        else:
            cross_component = _clip(cross_store_delta_pct, 0.0, 0.4) / 0.4

    score = (
        0.35 * hist_component
        + 0.25 * cross_component
        + 0.20 * (1.0 - (_clip(anchor_spike_pct, 0.0, 0.5) / 0.5))
        + 0.10 * duration_score
        + 0.10 * data_quality_score
    )

    anchor_anomaly_flag = anchor_spike_pct > 0.25

    if score >= 0.75 and r1 and r2 and r6:
        label = "REAL"
    elif score >= LIKELY_REAL_MIN_SCORE and r6:
        label = "LIKELY_REAL"
    elif score >= 0.40:
        label = "SUSPICIOUS"
    else:
        label = "LIKELY_FAKE"

    if anchor_anomaly_flag:
        label = "LIKELY_FAKE"

    return ScoreResult(
        score=round(score, 4),
        label=label,
        discount_pct=discount_pct,
        hist_delta_pct=hist_delta_pct,
        cross_store_delta_pct=cross_store_delta_pct,
        anchor_anomaly_flag=anchor_anomaly_flag,
        rule_trace={
            "R1_hist_delta_ge_15pct": r1,
            "R2_anchor_spike_le_10pct": r2,
            "R3_cross_store_ge_5pct": r3,
            "R4_seen_multiple_snapshots": r4,
            "R5_has_enough_history": r5,
            "R6_visible_discount_ge_10pct": r6,
            "anchor_spike_pct": round(anchor_spike_pct, 4),
            "cross_store_missing_is_neutral": cross_store_delta_pct is None,
        },
    )
