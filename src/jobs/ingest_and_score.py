from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from src.collectors.base import ProductOffer
from src.collectors.cruzverde_demo import collect_demo_cruzverde
from src.collectors.cruzverde_scraper import collect_cruzverde_skincare
from src.collectors.salcobrand_scraper import collect_salcobrand_skincare
from src.collectors.salcobrand_demo import collect_demo_salcobrand
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


def _with_history(offer: ProductOffer) -> list[ProductOffer]:
    # Demo helper: generate enough historical points to exercise scoring gates.
    multipliers = [1.55, 1.48, 1.42, 1.36, 1.30, 1.26, 1.22, 1.18, 1.14, 1.10, 1.06, 1.00]
    out: list[ProductOffer] = []
    for idx, mult in enumerate(multipliers):
        out.append(
            ProductOffer(
                retailer_name=offer.retailer_name,
                retailer_domain=offer.retailer_domain,
                retailer_product_id=offer.retailer_product_id,
                product_url=offer.product_url,
                title=offer.title,
                brand=offer.brand,
                size_raw=offer.size_raw,
                category_raw=offer.category_raw,
                price_current=round(offer.price_current * mult),
                price_list=offer.price_list,
                promo_text=offer.promo_text,
                in_stock=offer.in_stock,
                scraped_at=offer.scraped_at - timedelta(days=(len(multipliers) - 1 - idx)),
            )
        )
    return out


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
    if not salco_offers:
        salco_source = "fallback"
        salco_offers = collect_demo_salcobrand()
    offers.extend(salco_offers)

    try:
        cruzverde_offers = collect_cruzverde_skincare()
    except Exception as exc:
        cruzverde_offers = []
        cruzverde_error = str(exc)
    if not cruzverde_offers:
        cruzverde_source = "fallback"
        cruzverde_offers = collect_demo_cruzverde()
    offers.extend(cruzverde_offers)

    pending_evaluations: list[tuple[int, int, int, int, ProductOffer]] = []

    status = "SUCCESS"
    error_message: Optional[str] = None

    try:
        for offer in offers:
            retailer_id = upsert_retailer(offer.retailer_name, offer.retailer_domain)
            history_offers = _with_history(offer)

            for hist_offer in history_offers:
                raw_product_id = upsert_raw_product(retailer_id, hist_offer)
                canonical_id = ensure_canonical_product(raw_product_id, hist_offer)
                snapshot_id = insert_price_snapshot(raw_product_id, hist_offer)
                total_snapshots += 1
                pending_evaluations.append((raw_product_id, canonical_id, retailer_id, snapshot_id, hist_offer))

        for raw_product_id, canonical_id, retailer_id, snapshot_id, hist_offer in pending_evaluations:
            history_prices = fetch_price_history(raw_product_id)
            history_list_prices = fetch_list_history(raw_product_id)
            cross_prices = fetch_cross_store_latest(
                canonical_id,
                exclude_raw_product_id=raw_product_id,
            )

            score_in = ScoreInput(
                price_current=hist_offer.price_current,
                price_list=hist_offer.price_list,
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
