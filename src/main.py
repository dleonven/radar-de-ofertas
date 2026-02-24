from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from typing import Optional
from pathlib import Path

from src.api.schemas import Deal, DealListResponse, PipelineStatus
from src.db.migrate import run_migrations
from src.db.repository import fetch_latest_deals, fetch_latest_pipeline_run

app = FastAPI(title="Chilean Skincare Real-Discount API", version="0.1.0")
UI_DIR = Path(__file__).resolve().parent / "ui"

app.mount("/static", StaticFiles(directory=str(UI_DIR)), name="static")


@app.on_event("startup")
def startup() -> None:
    run_migrations()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/")
def dashboard() -> FileResponse:
    return FileResponse(UI_DIR / "index.html")


@app.get("/status/latest", response_model=Optional[PipelineStatus])
def get_latest_status() -> Optional[PipelineStatus]:
    row = fetch_latest_pipeline_run()
    if row is None:
        return None
    return PipelineStatus(**row)


@app.get("/deals", response_model=DealListResponse)
def get_deals(
    min_score: float = Query(default=0.0, ge=0.0, le=1.0),
    limit: int = Query(default=50, ge=1, le=200),
    label: Optional[str] = Query(default=None),
    retailer: Optional[str] = Query(default=None),
    brand: Optional[str] = Query(default=None),
    only_visible_discount_ge: Optional[float] = Query(default=None, ge=0.0, le=1.0),
    only_cross_store_positive: bool = Query(default=False),
) -> DealListResponse:
    rows = fetch_latest_deals(
        limit=limit,
        min_score=min_score,
        label=label,
        retailer=retailer,
        brand=brand,
        only_visible_discount_ge=only_visible_discount_ge,
        only_cross_store_positive=only_cross_store_positive,
    )
    items = [
        Deal(
            evaluation_id=int(row["id"]),
            retailer=row["retailer"],
            canonical_name=row["canonical_name"],
            brand=row["brand_norm"],
            product_url=row["product_url"],
            price_current=float(row["price_current"]),
            price_list=float(row["price_list"]) if row["price_list"] is not None else None,
            score=float(row["score"]),
            label=row["label"],
            discount_pct=float(row["discount_pct"]) if row["discount_pct"] is not None else None,
            hist_delta_pct=float(row["hist_delta_pct"]) if row["hist_delta_pct"] is not None else None,
            cross_store_delta_pct=(
                float(row["cross_store_delta_pct"]) if row["cross_store_delta_pct"] is not None else None
            ),
            created_at=row["created_at"],
            rule_trace=row["rule_trace"],
        )
        for row in rows
    ]
    return DealListResponse(items=items)
