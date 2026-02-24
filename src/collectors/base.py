from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass
class ProductOffer:
    retailer_name: str
    retailer_domain: str
    retailer_product_id: str
    product_url: str
    title: str
    brand: str
    size_raw: str
    category_raw: str
    price_current: float
    price_list: float | None
    promo_text: str | None
    in_stock: bool
    scraped_at: datetime
