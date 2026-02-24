from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.collectors.base import ProductOffer


def collect_demo_cruzverde() -> list[ProductOffer]:
    now = datetime.now(timezone.utc)
    return [
        ProductOffer(
            retailer_name="Cruz Verde",
            retailer_domain="cruzverde.cl",
            retailer_product_id="CV-CV-001",
            product_url="https://cruzverde.cl/producto/cerave-limpiador-473ml",
            title="CeraVe Limpiador Espumoso 473 ml",
            brand="CeraVe",
            size_raw="473 ml",
            category_raw="limpieza facial",
            price_current=13490,
            price_list=17990,
            promo_text="Oferta web",
            in_stock=True,
            scraped_at=now - timedelta(hours=4),
        ),
        ProductOffer(
            retailer_name="Cruz Verde",
            retailer_domain="cruzverde.cl",
            retailer_product_id="CV-LR-002",
            product_url="https://cruzverde.cl/producto/la-roche-posay-anthelios-50ml",
            title="La Roche-Posay Anthelios UVMune 400 Fluido 50 ml",
            brand="La Roche-Posay",
            size_raw="50 ml",
            category_raw="protector solar",
            price_current=15990,
            price_list=24990,
            promo_text="-36%",
            in_stock=True,
            scraped_at=now - timedelta(hours=3),
        ),
        ProductOffer(
            retailer_name="Cruz Verde",
            retailer_domain="cruzverde.cl",
            retailer_product_id="CV-VY-003",
            product_url="https://cruzverde.cl/producto/vichy-mineral-89-50ml",
            title="Vichy Mineral 89 Serum 50 ml",
            brand="Vichy",
            size_raw="50 ml",
            category_raw="serum",
            price_current=29490,
            price_list=29990,
            promo_text=None,
            in_stock=True,
            scraped_at=now - timedelta(hours=2),
        ),
    ]
