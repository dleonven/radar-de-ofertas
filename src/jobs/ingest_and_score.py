from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from src.collectors.base import ProductOffer
from src.collectors.cruzverde_scraper import collect_cruzverde_skincare
from src.collectors.salcobrand_scraper import collect_salcobrand_skincare
from src.db.migrate import run_migrations
from src.db.repository import (
    create_evaluation,
    ensure_canonical_product,
    fetch_cross_store_latest,
    fetch_list_history,
    fetch_price_history,
    create_pipeline_run,
    insert_price_snapshot,
    upsert_raw_product,
    upsert_retailer,
)
from src.scoring.engine import SCORING_VERSION, ScoreInput, evaluate_discount


def run_pipeline() -> None:
    run_migrations()
    started_at = datetime.now(timezone.utc)
    offers: list[ProductOffer] = []
    salco_source = "live"
    salco_error: Optional[str] = None
    cruzverde_source = "live"
    cruzverde_error: Optional[str] = None
    total_snapshots = 0
    total_evaluations = 0

    try:
        salco_offers = collect_salcobrand_skincare()
    except Exception as exc:
        salco_offers = []
        salco_error = str(exc)
        salco_source = "error"
    if not salco_offers:
        salco_source = "error"
        salco_error = salco_error or "Scraper returned no offers."
    offers.extend(salco_offers)

    try:
        cruzverde_offers = collect_cruzverde_skincare()
    except Exception as exc:
        cruzverde_offers = []
        cruzverde_error = str(exc)
        cruzverde_source = "error"
    if not cruzverde_offers:
        cruzverde_source = "error"
        cruzverde_error = cruzverde_error or "Scraper returned no offers."
    offers.extend(cruzverde_offers)

    print(
        "collector_summary",
        {
            "salcobrand_count": len(salco_offers),
            "salcobrand_error": salco_error,
            "cruzverde_count": len(cruzverde_offers),
            "cruzverde_error": cruzverde_error,
            "total_offers": len(offers),
        },
    )

    pending_evaluations: list[tuple[int, int, int, int, ProductOffer]] = []

    status = "SUCCESS"
    error_message: Optional[str] = None

    try:
        if not offers:
            raise RuntimeError(
                f"Real scraping required. Salcobrand error={salco_error!r}; Cruz Verde error={cruzverde_error!r}"
            )

        for offer in offers:
            retailer_id = upsert_retailer(offer.retailer_name, offer.retailer_domain)
            raw_product_id = upsert_raw_product(retailer_id, offer)
            canonical_id = ensure_canonical_product(raw_product_id, offer)
            snapshot_id = insert_price_snapshot(raw_product_id, offer)
            total_snapshots += 1
            pending_evaluations.append((raw_product_id, canonical_id, retailer_id, snapshot_id, offer))

        for raw_product_id, canonical_id, retailer_id, snapshot_id, offer in pending_evaluations:
            history_prices = fetch_price_history(raw_product_id)
            history_list_prices = fetch_list_history(raw_product_id)
            cross_prices = fetch_cross_store_latest(
                canonical_id,
                exclude_raw_product_id=raw_product_id,
            )

            score_in = ScoreInput(
                price_current=offer.price_current,
                price_list=offer.price_list,
                history_prices=history_prices,
                history_list_prices=history_list_prices,
                cross_store_prices=cross_prices,
                snapshot_count_recent=min(len(history_prices), 6),
            )
            result = evaluate_discount(score_in)

            create_evaluation(
                product_canonical_id=canonical_id,
                retailer_id=retailer_id,
                snapshot_id=snapshot_id,
                score=result.score,
                label=result.label,
                discount_pct=result.discount_pct,
                hist_delta_pct=result.hist_delta_pct,
                cross_store_delta_pct=result.cross_store_delta_pct,
                anchor_anomaly_flag=result.anchor_anomaly_flag,
                rule_trace=result.rule_trace,
                scoring_version=SCORING_VERSION,
            )
            total_evaluations += 1
    except Exception as exc:
        status = "FAILED"
        error_message = str(exc)
        raise
    finally:
        finished_at = datetime.now(timezone.utc)
        create_pipeline_run(
            started_at=started_at.isoformat(),
            finished_at=finished_at.isoformat(),
            status=status,
            total_offers=len(offers),
            total_snapshots=total_snapshots,
            total_evaluations=total_evaluations,
            salcobrand_source=salco_source,
            salcobrand_count=len(salco_offers),
            salcobrand_error=salco_error,
            cruzverde_source=cruzverde_source,
            cruzverde_count=len(cruzverde_offers),
            cruzverde_error=cruzverde_error,
            error_message=error_message,
        )


if __name__ == "__main__":
    run_pipeline()
    print(f"Pipeline completed at {datetime.now(timezone.utc).isoformat()}")
