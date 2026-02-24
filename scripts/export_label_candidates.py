from __future__ import annotations

import argparse
import csv
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.connection import get_conn


def main() -> None:
    parser = argparse.ArgumentParser(description="Export latest deals to labeling CSV.")
    parser.add_argument("--out", default="data/labels_candidates.csv")
    parser.add_argument("--db", default=None)
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()

    if args.db:
        os.environ["APP_DB_PATH"] = args.db

    with get_conn() as conn:
        rows = conn.execute(
            """
            SELECT
              pr.product_url,
              r.name AS retailer,
              de.label AS label_model,
              de.score,
              de.discount_pct,
              de.cross_store_delta_pct,
              de.created_at
            FROM discount_evaluations de
            JOIN price_snapshots ps ON ps.id = de.snapshot_id
            JOIN products_raw pr ON pr.id = ps.product_raw_id
            JOIN retailers r ON r.id = de.retailer_id
            JOIN (
              SELECT ps2.product_raw_id, MAX(ps2.scraped_at) AS max_scraped
              FROM price_snapshots ps2
              GROUP BY ps2.product_raw_id
            ) latest ON latest.product_raw_id = ps.product_raw_id AND latest.max_scraped = ps.scraped_at
            ORDER BY de.created_at DESC
            LIMIT ?
            """,
            (args.limit,),
        ).fetchall()

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "product_url",
                "retailer",
                "label_human",
                "notes",
                "label_model",
                "score",
                "discount_pct",
                "cross_store_delta_pct",
                "created_at",
            ]
        )
        for r in rows:
            writer.writerow(
                [
                    r["product_url"],
                    r["retailer"],
                    "",
                    "",
                    r["label_model"],
                    r["score"],
                    r["discount_pct"],
                    r["cross_store_delta_pct"],
                    r["created_at"],
                ]
            )

    print("Exported", len(rows), "rows to", str(out_path))


if __name__ == "__main__":
    main()
