from __future__ import annotations

import argparse
import csv
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.db.connection import get_conn

VALID_LABELS = {"REAL", "LIKELY_REAL", "SUSPICIOUS", "LIKELY_FAKE", "FAKE"}
POSITIVE_HUMAN = {"REAL"}
POSITIVE_MODEL = {"REAL", "LIKELY_REAL"}


@dataclass
class LabeledRow:
    product_url: str
    retailer: str
    label_human: str
    notes: str


@dataclass
class PredictedRow:
    label_pred: str
    score: float
    discount_pct: Optional[float]
    cross_store_delta_pct: Optional[float]


def load_labels(csv_path: str) -> List[LabeledRow]:
    rows: List[LabeledRow] = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        required = {"product_url", "retailer", "label_human", "notes"}
        missing = required.difference(set(reader.fieldnames or []))
        if missing:
            raise ValueError("Missing CSV columns: %s" % ", ".join(sorted(missing)))

        for line in reader:
            product_url = (line.get("product_url") or "").strip()
            retailer = (line.get("retailer") or "").strip()
            label_human = (line.get("label_human") or "").strip().upper()
            notes = (line.get("notes") or "").strip()

            if not product_url or not retailer or not label_human:
                continue
            if label_human not in VALID_LABELS:
                raise ValueError("Invalid label_human '%s' in row for %s" % (label_human, product_url))

            rows.append(
                LabeledRow(
                    product_url=product_url,
                    retailer=retailer,
                    label_human=label_human,
                    notes=notes,
                )
            )
    return rows


def fetch_latest_predictions() -> Dict[Tuple[str, str], PredictedRow]:
    with get_conn() as conn:
        db_rows = conn.execute(
            """
            SELECT
              pr.product_url,
              r.name AS retailer,
              de.label,
              de.score,
              de.discount_pct,
              de.cross_store_delta_pct
            FROM discount_evaluations de
            JOIN price_snapshots ps ON ps.id = de.snapshot_id
            JOIN products_raw pr ON pr.id = ps.product_raw_id
            JOIN retailers r ON r.id = de.retailer_id
            JOIN (
              SELECT ps2.product_raw_id, MAX(ps2.scraped_at) AS max_scraped
              FROM price_snapshots ps2
              GROUP BY ps2.product_raw_id
            ) latest ON latest.product_raw_id = ps.product_raw_id AND latest.max_scraped = ps.scraped_at
            """
        ).fetchall()

    out: Dict[Tuple[str, str], PredictedRow] = {}
    for row in db_rows:
        key = (str(row["product_url"]).strip(), str(row["retailer"]).strip().lower())
        out[key] = PredictedRow(
            label_pred=str(row["label"]),
            score=float(row["score"]),
            discount_pct=float(row["discount_pct"]) if row["discount_pct"] is not None else None,
            cross_store_delta_pct=(
                float(row["cross_store_delta_pct"]) if row["cross_store_delta_pct"] is not None else None
            ),
        )
    return out


def safe_div(num: int, den: int) -> float:
    if den == 0:
        return 0.0
    return num / den


def sweep_thresholds(
    joined_rows: List[Tuple[LabeledRow, PredictedRow]],
    thresholds: List[float],
) -> None:
    print("\nThreshold Sweep (predict positive if score >= t and visible discount gate satisfied)")
    print("- ranking: precision desc, recall desc, threshold asc")

    ranked: List[Tuple[float, float, float, int, int, float]] = []
    for t in thresholds:
        tp = fp = fn = tn = 0
        for human, pred in joined_rows:
            human_pos = human.label_human in POSITIVE_HUMAN
            visible_ok = (pred.discount_pct or 0.0) >= 0.10
            pred_pos = (pred.score >= t) and visible_ok

            if human_pos and pred_pos:
                tp += 1
            elif (not human_pos) and pred_pos:
                fp += 1
            elif human_pos and (not pred_pos):
                fn += 1
            else:
                tn += 1

        precision = safe_div(tp, tp + fp)
        recall = safe_div(tp, tp + fn)
        ranked.append((precision, recall, t, tp, fp, safe_div(tp + tn, tp + fp + fn + tn)))

    ranked.sort(key=lambda x: (-x[0], -x[1], x[2]))

    for precision, recall, t, tp, fp, accuracy in ranked:
        print(
            "- t=%.2f precision=%.4f recall=%.4f accuracy=%.4f tp=%d fp=%d"
            % (t, precision, recall, accuracy, tp, fp)
        )

    best = ranked[0]
    print(
        "\nRecommended threshold: %.2f (precision=%.4f, recall=%.4f, accuracy=%.4f)"
        % (best[2], best[0], best[1], best[5])
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare human labels vs model predictions.")
    parser.add_argument("--csv", default="data/labels_template.csv", help="Path to labels CSV")
    parser.add_argument("--db", default=None, help="DB path override (or use APP_DB_PATH)")
    parser.add_argument("--sweep", action="store_true", help="Run threshold sweep report")
    args = parser.parse_args()

    if args.db:
        os.environ["APP_DB_PATH"] = args.db

    labels = load_labels(args.csv)
    preds = fetch_latest_predictions()

    total = 0
    matched = 0
    missing = 0
    exact = 0

    tp = fp = fn = tn = 0

    confusion: Dict[Tuple[str, str], int] = defaultdict(int)
    mismatches: List[str] = []
    joined_rows: List[Tuple[LabeledRow, PredictedRow]] = []

    for row in labels:
        total += 1
        key = (row.product_url, row.retailer.lower())
        pred = preds.get(key)
        if pred is None:
            missing += 1
            mismatches.append(
                "MISSING prediction | retailer=%s | url=%s | human=%s" % (row.retailer, row.product_url, row.label_human)
            )
            continue

        matched += 1
        joined_rows.append((row, pred))
        confusion[(row.label_human, pred.label_pred)] += 1
        if row.label_human == pred.label_pred:
            exact += 1

        human_pos = row.label_human in POSITIVE_HUMAN
        pred_pos = pred.label_pred in POSITIVE_MODEL

        if human_pos and pred_pos:
            tp += 1
        elif (not human_pos) and pred_pos:
            fp += 1
        elif human_pos and (not pred_pos):
            fn += 1
        else:
            tn += 1

        if row.label_human != pred.label_pred:
            mismatches.append(
                "MISMATCH | retailer=%s | human=%s | pred=%s | score=%.4f | discount=%s | cross=%s | url=%s"
                % (
                    row.retailer,
                    row.label_human,
                    pred.label_pred,
                    pred.score,
                    "%.4f" % pred.discount_pct if pred.discount_pct is not None else "null",
                    "%.4f" % pred.cross_store_delta_pct if pred.cross_store_delta_pct is not None else "null",
                    row.product_url,
                )
            )

    precision = safe_div(tp, tp + fp)
    recall = safe_div(tp, tp + fn)
    accuracy = safe_div(exact, matched)

    print("Calibration Summary")
    print("- csv_rows:", total)
    print("- matched_rows:", matched)
    print("- missing_rows:", missing)
    print("- exact_match_accuracy:", "%.4f" % accuracy)
    print("- positive_precision (REAL vs REAL/LIKELY_REAL):", "%.4f" % precision)
    print("- positive_recall (REAL vs REAL/LIKELY_REAL):", "%.4f" % recall)

    print("\nBinary Confusion (positive=human REAL, predicted REAL/LIKELY_REAL)")
    print("- TP:", tp)
    print("- FP:", fp)
    print("- FN:", fn)
    print("- TN:", tn)

    print("\nLabel Confusion Matrix (human -> predicted)")
    labels_seen: Set[str] = set()
    for human, pred in confusion.keys():
        labels_seen.add(human)
        labels_seen.add(pred)

    for human in sorted(labels_seen):
        counts: List[str] = []
        for pred in sorted(labels_seen):
            c = confusion.get((human, pred), 0)
            if c:
                counts.append("%s:%d" % (pred, c))
        if counts:
            print("- %s -> %s" % (human, ", ".join(counts)))

    if mismatches:
        print("\nMismatches")
        for line in mismatches:
            print("-", line)

    if args.sweep and joined_rows:
        thresholds = [round(x / 100, 2) for x in range(50, 71, 1)]
        sweep_thresholds(joined_rows, thresholds)


if __name__ == "__main__":
    main()
