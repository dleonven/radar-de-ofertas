from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.collectors.base import ProductOffer


def collect_demo_salcobrand() -> list[ProductOffer]:
    now = datetime.now(timezone.utc)
    return [
        ProductOffer(
            retailer_name="Salcobrand",
            retailer_domain="salcobrand.cl",
            retailer_product_id="SB-CV-001",
            product_url="https://salcobrand.cl/producto/cerave-limpiador-473ml",
            title="CeraVe Limpiador Espumoso 473 ml",
            brand="CeraVe",
            size_raw="473 ml",
            category_raw="limpieza facial",
            price_current=12990,
            price_list=17990,
            promo_text="Oferta online",
            in_stock=True,
            scraped_at=now - timedelta(hours=4),
        ),
        ProductOffer(
            retailer_name="Salcobrand",
            retailer_domain="salcobrand.cl",
            retailer_product_id="SB-LR-002",
            product_url="https://salcobrand.cl/producto/la-roche-posay-anthelios-50ml",
            title="La Roche-Posay Anthelios UVMune 400 Fluido 50 ml",
            brand="La Roche-Posay",
            size_raw="50 ml",
            category_raw="protector solar",
            price_current=14990,
            price_list=24990,
            promo_text="-40%",
            in_stock=True,
            scraped_at=now - timedelta(hours=3),
        ),
        ProductOffer(
            retailer_name="Salcobrand",
            retailer_domain="salcobrand.cl",
            retailer_product_id="SB-VY-003",
            product_url="https://salcobrand.cl/producto/vichy-mineral-89-50ml",
            title="Vichy Mineral 89 Serum 50 ml",
            brand="Vichy",
            size_raw="50 ml",
            category_raw="serum",
            price_current=28990,
            price_list=29990,
            promo_text=None,
            in_stock=True,
            scraped_at=now - timedelta(hours=2),
        ),
    ]
