from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

URL_HINT_RE = re.compile(r"api|graphql|search|products|catalog|plp|price", re.IGNORECASE)
BODY_HINT_RE = re.compile(r"price|precio|product|producto|sku|ean|brand|marca", re.IGNORECASE)


def load_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def analyze(path: Path) -> None:
    responses = []
    for event in load_jsonl(path):
        if event.get("type") != "response":
            continue
        responses.append(event)

    print(f"file: {path}")
    print(f"responses: {len(responses)}")

    status_counts = Counter(r.get("status") for r in responses)
    print("status_counts:", dict(status_counts))

    candidate_scores = defaultdict(int)
    samples = {}

    for r in responses:
        url = r.get("url") or ""
        ct = (r.get("content_type") or "").lower()
        body = r.get("body_preview") or ""
        score = 0

        if URL_HINT_RE.search(url):
            score += 2
        if "json" in ct:
            score += 2
        if BODY_HINT_RE.search(body):
            score += 2
        if r.get("status") == 200:
            score += 1

        if score > 0:
            candidate_scores[url] += score
            samples[url] = body[:500] if body else ""

    ranked = sorted(candidate_scores.items(), key=lambda x: x[1], reverse=True)

    print("\nTop endpoint candidates:")
    for url, score in ranked[:20]:
        print(f"- score={score:>3}  {url}")

    print("\nCandidate payload previews:")
    shown = 0
    for url, _ in ranked[:10]:
        body = samples.get(url, "")
        if not body:
            continue
        print(f"\nURL: {url}")
        print(body.replace("\n", " ")[:500])
        shown += 1
        if shown >= 5:
            break


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze captured API traffic JSONL files.")
    parser.add_argument("paths", nargs="+", help="One or more .jsonl capture files")
    args = parser.parse_args()

    for p in args.paths:
        analyze(Path(p))
        print("\n" + "=" * 80 + "\n")


if __name__ == "__main__":
    main()
