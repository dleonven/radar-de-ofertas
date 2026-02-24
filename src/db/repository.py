from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from typing import Any

from src.collectors.base import ProductOffer
from src.db.connection import get_conn, is_postgres
from src.normalization.product import canonical_key, parse_size


def upsert_retailer(name: str, domain: str) -> int:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO retailers (name, domain) VALUES (?, ?)
            ON CONFLICT(domain) DO UPDATE SET name = excluded.name
            """,
            (name, domain),
        )
        row = conn.execute("SELECT id FROM retailers WHERE domain = ?", (domain,)).fetchone()
        return int(row["id"])


def upsert_raw_product(retailer_id: int, offer: ProductOffer) -> int:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO products_raw (
              retailer_id, retailer_product_id, product_url, title, brand_raw, size_raw, category_raw, last_seen_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(retailer_id, retailer_product_id)
            DO UPDATE SET
              product_url = excluded.product_url,
              title = excluded.title,
              brand_raw = excluded.brand_raw,
              size_raw = excluded.size_raw,
              category_raw = excluded.category_raw,
              last_seen_at = excluded.last_seen_at
            """,
            (
                retailer_id,
                offer.retailer_product_id,
                offer.product_url,
                offer.title,
                offer.brand,
                offer.size_raw,
                offer.category_raw,
                datetime.now(timezone.utc).isoformat(),
            ),
        )
        row = conn.execute(
            "SELECT id FROM products_raw WHERE retailer_id = ? AND retailer_product_id = ?",
            (retailer_id, offer.retailer_product_id),
        ).fetchone()
        return int(row["id"])


def ensure_canonical_product(raw_product_id: int, offer: ProductOffer) -> int:
    brand_norm, title_norm, size_value, size_unit = canonical_key(offer.brand, offer.title, offer.size_raw)
    with get_conn() as conn:
        found = conn.execute(
            """
            SELECT id FROM products_canonical
            WHERE brand_norm = ? AND canonical_name = ?
              AND COALESCE(size_value, -1) = COALESCE(?, -1)
              AND COALESCE(size_unit, '') = COALESCE(?, '')
            """,
            (brand_norm, title_norm, size_value, size_unit),
        ).fetchone()

        if found is None:
            category_norm = "skincare"
            size_v, size_u = parse_size(offer.size_raw)
            conn.execute(
                """
                INSERT INTO products_canonical (
                  canonical_name, brand_norm, size_value, size_unit, category_norm
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (title_norm, brand_norm, size_v, size_u, category_norm),
            )
            found = conn.execute(
                """
                SELECT id FROM products_canonical
                WHERE brand_norm = ? AND canonical_name = ?
                ORDER BY id DESC LIMIT 1
                """,
                (brand_norm, title_norm),
            ).fetchone()

        canonical_id = int(found["id"])

        has_match = conn.execute(
            """
            SELECT id FROM product_matches
            WHERE product_raw_id = ? AND product_canonical_id = ?
            LIMIT 1
            """,
            (raw_product_id, canonical_id),
        ).fetchone()

        if has_match is None:
            conn.execute(
                """
                INSERT INTO product_matches (
                  product_raw_id, product_canonical_id, match_confidence, match_method, status
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (raw_product_id, canonical_id, 0.98, "rule", "AUTO_ACCEPTED"),
            )

        return canonical_id


def insert_price_snapshot(raw_product_id: int, offer: ProductOffer) -> int:
    source_hash = sha256(
        f"{offer.retailer_product_id}|{offer.price_current}|{offer.price_list}|{offer.scraped_at.isoformat()}".encode("utf-8")
    ).hexdigest()
    with get_conn() as conn:
        if is_postgres():
            conn.execute(
                """
                INSERT INTO price_snapshots (
                  product_raw_id, scraped_at, price_current, price_list, currency, promo_text, in_stock, source_hash
                ) VALUES (?, ?, ?, ?, 'CLP', ?, ?, ?)
                ON CONFLICT(product_raw_id, scraped_at) DO NOTHING
                """,
                (
                    raw_product_id,
                    offer.scraped_at.isoformat(),
                    offer.price_current,
                    offer.price_list,
                    offer.promo_text,
                    bool(offer.in_stock),
                    source_hash,
                ),
            )
        else:
            conn.execute(
                """
                INSERT OR IGNORE INTO price_snapshots (
                  product_raw_id, scraped_at, price_current, price_list, currency, promo_text, in_stock, source_hash
                ) VALUES (?, ?, ?, ?, 'CLP', ?, ?, ?)
                """,
                (
                    raw_product_id,
                    offer.scraped_at.isoformat(),
                    offer.price_current,
                    offer.price_list,
                    offer.promo_text,
                    int(offer.in_stock),
                    source_hash,
                ),
            )
        row = conn.execute(
            """
            SELECT id FROM price_snapshots
            WHERE product_raw_id = ? AND scraped_at = ?
            """,
            (raw_product_id, offer.scraped_at.isoformat()),
        ).fetchone()
        return int(row["id"])


def create_evaluation(
    *,
    product_canonical_id: int,
    retailer_id: int,
    snapshot_id: int,
    score: float,
    label: str,
    discount_pct: float | None,
    hist_delta_pct: float | None,
    cross_store_delta_pct: float | None,
    anchor_anomaly_flag: bool,
    rule_trace: dict[str, Any],
    scoring_version: str,
) -> None:
    with get_conn() as conn:
        exists = conn.execute(
            """
            SELECT id FROM discount_evaluations
            WHERE snapshot_id = ? AND scoring_version = ?
            LIMIT 1
            """,
            (snapshot_id, scoring_version),
        ).fetchone()
        if exists is not None:
            return

        conn.execute(
            """
            INSERT INTO discount_evaluations (
              product_canonical_id, retailer_id, snapshot_id, score, label,
              discount_pct, hist_delta_pct, cross_store_delta_pct,
              anchor_anomaly_flag, rule_trace, scoring_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                product_canonical_id,
                retailer_id,
                snapshot_id,
                score,
                label,
                discount_pct,
                hist_delta_pct,
                cross_store_delta_pct,
                bool(anchor_anomaly_flag) if is_postgres() else int(anchor_anomaly_flag),
                json.dumps(rule_trace),
                scoring_version,
            ),
        )


def fetch_price_history(raw_product_id: int, limit: int = 120) -> list[float]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT price_current FROM price_snapshots
            WHERE product_raw_id = ?
            ORDER BY scraped_at DESC
            LIMIT ?
            """,
            (raw_product_id, limit),
        ).fetchall()
        return [float(r["price_current"]) for r in rows]


def fetch_list_history(raw_product_id: int, limit: int = 120) -> list[float]:
    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT price_list FROM price_snapshots
            WHERE product_raw_id = ? AND price_list IS NOT NULL
            ORDER BY scraped_at DESC
            LIMIT ?
            """,
            (raw_product_id, limit),
        ).fetchall()
        return [float(r["price_list"]) for r in rows]


def fetch_cross_store_latest(
    canonical_id: int,
    *,
    exclude_raw_product_id: int | None = None,
    lookback_limit: int = 20,
) -> list[float]:
    with get_conn() as conn:
        where_exclude = ""
        params: list[Any] = [canonical_id, canonical_id]
        if exclude_raw_product_id is not None:
            where_exclude = " AND pm.product_raw_id != ?"
            params.append(exclude_raw_product_id)
        params.append(lookback_limit)

        rows = conn.execute(
            f"""
            SELECT ps.price_current
            FROM product_matches pm
            JOIN (
              SELECT p1.product_raw_id, MAX(ps1.scraped_at) AS max_scraped
              FROM product_matches p1
              JOIN price_snapshots ps1 ON ps1.product_raw_id = p1.product_raw_id
              WHERE p1.product_canonical_id = ?
              GROUP BY p1.product_raw_id
            ) latest ON latest.product_raw_id = pm.product_raw_id
            JOIN price_snapshots ps ON ps.product_raw_id = latest.product_raw_id AND ps.scraped_at = latest.max_scraped
            WHERE pm.product_canonical_id = ?
            {where_exclude}
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()
        return [float(r["price_current"]) for r in rows]


def fetch_latest_deals(
    *,
    limit: int = 50,
    min_score: float = 0.0,
    label: str | None = None,
    retailer: str | None = None,
    brand: str | None = None,
    only_visible_discount_ge: float | None = None,
    only_cross_store_positive: bool = False,
) -> list[dict[str, Any]]:
    conditions = [
        "de.score >= ?",
        "de.snapshot_id = ps_latest.id",
    ]
    params: list[Any] = [min_score]

    if label:
        conditions.append("de.label = ?")
        params.append(label)
    if retailer:
        conditions.append("LOWER(r.name) = LOWER(?)")
        params.append(retailer)
    if brand:
        conditions.append("LOWER(pc.brand_norm) = LOWER(?)")
        params.append(brand)
    if only_visible_discount_ge is not None:
        conditions.append("de.discount_pct IS NOT NULL AND de.discount_pct >= ?")
        params.append(only_visible_discount_ge)
    if only_cross_store_positive:
        conditions.append("de.cross_store_delta_pct IS NOT NULL AND de.cross_store_delta_pct > 0")

    where_clause = " AND ".join(conditions)
    params.append(limit)

    with get_conn() as conn:
        rows = conn.execute(
            f"""
            SELECT
              de.id,
              de.score,
              de.label,
              de.discount_pct,
              de.hist_delta_pct,
              de.cross_store_delta_pct,
              de.rule_trace,
              de.created_at,
              r.name AS retailer,
              pc.canonical_name,
              pc.brand_norm,
              pr.product_url,
              ps.price_current,
              ps.price_list
            FROM discount_evaluations de
            JOIN (
              SELECT product_raw_id, MAX(scraped_at) AS max_scraped_at
              FROM price_snapshots
              GROUP BY product_raw_id
            ) latest_snap
              ON latest_snap.product_raw_id = (
                SELECT product_raw_id FROM price_snapshots WHERE id = de.snapshot_id
              )
            JOIN price_snapshots ps_latest
              ON ps_latest.product_raw_id = latest_snap.product_raw_id
             AND ps_latest.scraped_at = latest_snap.max_scraped_at
            JOIN retailers r ON r.id = de.retailer_id
            JOIN products_canonical pc ON pc.id = de.product_canonical_id
            JOIN price_snapshots ps ON ps.id = de.snapshot_id
            JOIN products_raw pr ON pr.id = ps.product_raw_id
            WHERE {where_clause}
            ORDER BY de.created_at DESC
            LIMIT ?
            """,
            tuple(params),
        ).fetchall()

    return [dict(row) for row in rows]


def create_pipeline_run(
    *,
    started_at: str,
    finished_at: str,
    status: str,
    total_offers: int,
    total_snapshots: int,
    total_evaluations: int,
    salcobrand_source: str,
    salcobrand_count: int,
    salcobrand_error: str | None,
    cruzverde_source: str,
    cruzverde_count: int,
    cruzverde_error: str | None,
    falabella_source: str,
    falabella_count: int,
    falabella_error: str | None,
    error_message: str | None,
) -> None:
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO pipeline_runs (
              started_at, finished_at, status, total_offers, total_snapshots, total_evaluations,
              salcobrand_source, salcobrand_count, salcobrand_error,
              cruzverde_source, cruzverde_count, cruzverde_error,
              falabella_source, falabella_count, falabella_error,
              error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                started_at,
                finished_at,
                status,
                total_offers,
                total_snapshots,
                total_evaluations,
                salcobrand_source,
                salcobrand_count,
                salcobrand_error,
                cruzverde_source,
                cruzverde_count,
                cruzverde_error,
                falabella_source,
                falabella_count,
                falabella_error,
                error_message,
            ),
        )


def fetch_latest_pipeline_run() -> dict[str, Any] | None:
    with get_conn() as conn:
        row = conn.execute(
            """
            SELECT
              id,
              started_at,
              finished_at,
              status,
              total_offers,
              total_snapshots,
              total_evaluations,
              salcobrand_source,
              salcobrand_count,
              salcobrand_error,
              cruzverde_source,
              cruzverde_count,
              cruzverde_error,
              falabella_source,
              falabella_count,
              falabella_error,
              error_message,
              created_at
            FROM pipeline_runs
            ORDER BY created_at DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return dict(row)
