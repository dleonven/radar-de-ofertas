from src.scoring.engine import ScoreInput, evaluate_discount


def test_scoring_flags_anchor_spike_as_fake() -> None:
    result = evaluate_discount(
        ScoreInput(
            price_current=10000,
            price_list=25000,
            history_prices=[12000, 11800, 11900, 12100],
            history_list_prices=[15000, 15200, 14900],
            cross_store_prices=[11500, 11700],
            snapshot_count_recent=3,
        )
    )
    assert result.label == "LIKELY_FAKE"
    assert result.anchor_anomaly_flag is True


def test_low_visible_discount_cannot_be_likely_real() -> None:
    result = evaluate_discount(
        ScoreInput(
            price_current=28990,
            price_list=29990,  # ~3.3% visible discount
            history_prices=[35500, 34800, 34000, 33200, 32500, 31900, 31000, 30300, 29600, 29200],
            history_list_prices=[29990, 29990, 29990, 29990],
            cross_store_prices=[],
            snapshot_count_recent=4,
        )
    )
    assert result.rule_trace["R6_visible_discount_ge_10pct"] is False
    assert result.label in {"SUSPICIOUS", "LIKELY_FAKE"}
