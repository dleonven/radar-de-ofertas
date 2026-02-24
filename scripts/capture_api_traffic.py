from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from playwright.sync_api import sync_playwright

TARGETS = {
    "salcobrand": "https://www.salcobrand.cl/cuidado-de-la-piel",
    "cruzverde": "https://www.cruzverde.cl/cuidado-facial",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_text(response, max_chars: int) -> str | None:
    try:
        body = response.text()
    except Exception:
        return None
    if body is None:
        return None
    body = body.strip()
    if len(body) > max_chars:
        return body[:max_chars]
    return body


def capture_target(
    *,
    retailer: str,
    start_url: str,
    wait_seconds: int,
    max_chars: int,
    out_dir: Path,
    headless: bool,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"network_capture_{retailer}.jsonl"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="es-CL",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        with out_path.open("w", encoding="utf-8") as f:
            def log_event(event: Dict[str, Any]) -> None:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

            def on_request(req) -> None:
                if req.resource_type not in {"xhr", "fetch", "document"}:
                    return
                headers = req.headers
                body = req.post_data
                if body and len(body) > max_chars:
                    body = body[:max_chars]
                log_event(
                    {
                        "ts": now_iso(),
                        "type": "request",
                        "retailer": retailer,
                        "url": req.url,
                        "method": req.method,
                        "resource_type": req.resource_type,
                        "headers": headers,
                        "post_data": body,
                    }
                )

            def on_response(res) -> None:
                req = res.request
                if req.resource_type not in {"xhr", "fetch", "document"}:
                    return
                ct = (res.headers.get("content-type") or "").lower()
                body_preview = None
                if "json" in ct or "javascript" in ct or "text" in ct:
                    body_preview = safe_text(res, max_chars=max_chars)
                log_event(
                    {
                        "ts": now_iso(),
                        "type": "response",
                        "retailer": retailer,
                        "url": res.url,
                        "method": req.method,
                        "resource_type": req.resource_type,
                        "status": res.status,
                        "content_type": ct,
                        "headers": res.headers,
                        "body_preview": body_preview,
                    }
                )

            page.on("request", on_request)
            page.on("response", on_response)

            start = time.time()
            try:
                page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
            except Exception as exc:
                log_event(
                    {
                        "ts": now_iso(),
                        "type": "navigate_error",
                        "retailer": retailer,
                        "url": start_url,
                        "error": str(exc),
                    }
                )

            # Let SPA/network settle.
            while time.time() - start < wait_seconds:
                page.wait_for_timeout(500)

        context.close()
        browser.close()

    return out_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Capture retailer API traffic using Playwright.")
    parser.add_argument("--retailer", choices=["salcobrand", "cruzverde", "all"], default="all")
    parser.add_argument("--wait-seconds", type=int, default=18)
    parser.add_argument("--max-chars", type=int, default=8000)
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser")
    args = parser.parse_args()

    targets = TARGETS if args.retailer == "all" else {args.retailer: TARGETS[args.retailer]}
    out_dir = Path(args.out_dir)

    for retailer, url in targets.items():
        out = capture_target(
            retailer=retailer,
            start_url=url,
            wait_seconds=args.wait_seconds,
            max_chars=args.max_chars,
            out_dir=out_dir,
            headless=not args.headed,
        )
        print(f"captured {retailer} -> {out}")


if __name__ == "__main__":
    main()
