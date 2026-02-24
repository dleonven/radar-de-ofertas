from typing import List, Optional
from pydantic import BaseModel


class Deal(BaseModel):
    evaluation_id: int
    retailer: str
    canonical_name: str
    brand: str
    product_url: str
    price_current: float
    price_list: Optional[float]
    score: float
    label: str
    discount_pct: Optional[float]
    hist_delta_pct: Optional[float]
    cross_store_delta_pct: Optional[float]
    created_at: str
    rule_trace: str


class DealListResponse(BaseModel):
    items: List[Deal]


class PipelineStatus(BaseModel):
    started_at: str
    finished_at: str
    status: str
    total_offers: int
    total_snapshots: int
    total_evaluations: int
    salcobrand_source: str
    salcobrand_count: int
    salcobrand_error: Optional[str]
    cruzverde_source: str
    cruzverde_count: int
    cruzverde_error: Optional[str]
    falabella_source: str
    falabella_count: int
    falabella_error: Optional[str]
    error_message: Optional[str]
    created_at: str
