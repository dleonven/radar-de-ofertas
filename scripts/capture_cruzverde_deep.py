from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import sync_playwright

BASE_URL = "https://www.cruzverde.cl/"
KEYWORDS = ("piel", "facial", "dermo", "skincare", "rostro", "hidrat", "solar")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def same_host(url: str, host: str) -> bool:
    try:
        return (urlparse(url).hostname or "") == host
    except Exception:
        return False


def should_log_url(url: str) -> bool:
    low = url.lower()
    return (
        "api.cruzverde.cl" in low
        or "contentful.com" in low
        or "product" in low
        or "catalog" in low
        or "search" in low
        or "graphql" in low
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Deep API capture for Cruz Verde.")
    parser.add_argument("--out-dir", default="data")
    parser.add_argument("--max-links", type=int, default=12)
    parser.add_argument("--wait-seconds", type=int, default=6)
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "network_capture_cruzverde_deep.jsonl"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            locale="es-CL",
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()

        with out_path.open("w", encoding="utf-8") as f:
            def emit(event: dict) -> None:
                f.write(json.dumps(event, ensure_ascii=False) + "\n")

            def on_request(req) -> None:
                if req.resource_type not in {"xhr", "fetch", "document", "script"}:
                    return
                if req.resource_type in {"xhr", "fetch"} or should_log_url(req.url):
                    body = req.post_data
                    if body and len(body) > 3000:
                        body = body[:3000]
                    emit(
                        {
                            "ts": now_iso(),
                            "type": "request",
                            "url": req.url,
                            "method": req.method,
                            "resource_type": req.resource_type,
                            "post_data": body,
                        }
                    )

            def on_response(res) -> None:
                req = res.request
                if req.resource_type not in {"xhr", "fetch", "document", "script"}:
                    return
                if req.resource_type in {"xhr", "fetch"} or should_log_url(res.url):
                    ct = (res.headers.get("content-type") or "").lower()
                    preview = None
                    if "json" in ct or "javascript" in ct or "text" in ct or req.resource_type == "script":
                        try:
                            preview = res.text()
                        except Exception:
                            preview = None
                        if preview and len(preview) > 8000:
                            preview = preview[:8000]
                    emit(
                        {
                            "ts": now_iso(),
                            "type": "response",
                            "url": res.url,
                            "status": res.status,
                            "method": req.method,
                            "resource_type": req.resource_type,
                            "content_type": ct,
                            "body_preview": preview,
                        }
                    )

            page.on("request", on_request)
            page.on("response", on_response)

            emit({"ts": now_iso(), "type": "phase", "name": "open_home", "url": BASE_URL})
            page.goto(BASE_URL, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(4000)

            host = urlparse(BASE_URL).hostname or "www.cruzverde.cl"
            raw_hrefs = page.eval_on_selector_all(
                "a[href]",
                "els => els.map(a => a.getAttribute('href')).filter(Boolean)",
            )
            candidates = []
            seen = set()
            for href in raw_hrefs:
                abs_url = urljoin(BASE_URL, href)
                low = abs_url.lower()
                if not same_host(abs_url, host):
                    continue
                if abs_url in seen:
                    continue
                if any(k in low for k in KEYWORDS):
                    seen.add(abs_url)
                    candidates.append(abs_url)

            emit({"ts": now_iso(), "type": "candidates", "count": len(candidates), "urls": candidates[:30]})

            for idx, url in enumerate(candidates[: args.max_links], start=1):
                emit({"ts": now_iso(), "type": "phase", "name": "visit_candidate", "index": idx, "url": url})
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=60000)
                except Exception as exc:
                    emit({"ts": now_iso(), "type": "navigate_error", "url": url, "error": str(exc)})
                    continue
                page.wait_for_timeout(args.wait_seconds * 1000)
                try:
                    page.mouse.wheel(0, 3500)
                    page.wait_for_timeout(1500)
                except Exception:
                    pass
                emit({
                    "ts": now_iso(),
                    "type": "page_state",
                    "requested_url": url,
                    "final_url": page.url,
                    "title": page.title(),
                })

        context.close()
        browser.close()

    print(f"capture_saved={out_path}")


if __name__ == "__main__":
    main()
