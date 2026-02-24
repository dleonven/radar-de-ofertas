from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from html import unescape
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from src.collectors.base import ProductOffer

DEFAULT_START_URL = "https://www.cruzverde.cl/cuidado-facial"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_PAGES = 3

_PRICE_RE = re.compile(r"(\d{1,3}(?:[\.,]\d{3})+|\d+)")
_HREF_RE = re.compile(r"href=[\"']([^\"']+/(?:producto|product|p)/[^\"']+)[\"']", re.IGNORECASE)
_TITLE_RE = re.compile(r"title=[\"']([^\"']+)[\"']", re.IGNORECASE)
_JSON_LD_RE = re.compile(
    r"<script[^>]*type=[\"']application/ld\+json[\"'][^>]*>(.*?)</script>",
    re.IGNORECASE | re.DOTALL,
)


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", unescape(value or "")).strip()


def _extract_price(value: str) -> Optional[float]:
    txt = _clean_text(value)
    if not txt:
        return None
    matches = _PRICE_RE.findall(txt)
    if not matches:
        return None
    token = matches[-1].replace(".", "").replace(",", "")
    try:
        return float(token)
    except ValueError:
        return None


def _fetch_html(url: str) -> str:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; discount-detector/0.1)",
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        },
    )
    with urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
        return resp.read().decode("utf-8", errors="ignore")


def _add_or_replace_query(url: str, key: str, value: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query[key] = value
    return urlunparse(parsed._replace(query=urlencode(query)))


def _page_urls(start_url: str, max_pages: int) -> list[str]:
    urls: list[str] = []
    for page in range(1, max_pages + 1):
        if page == 1:
            urls.append(start_url)
            continue
        urls.append(_add_or_replace_query(start_url, "page", str(page)))
        urls.append(_add_or_replace_query(start_url, "p", str(page)))

    deduped: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        deduped.append(u)
    return deduped


def _parse_from_json_ld(html: str, base_url: str, now: datetime, max_items: int) -> list[ProductOffer]:
    offers: list[ProductOffer] = []
    for match in _JSON_LD_RE.findall(html):
        raw = match.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        entries = payload if isinstance(payload, list) else [payload]
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if entry.get("@type") not in {"Product", "Offer", "ListItem"}:
                continue

            product = entry.get("item") if entry.get("@type") == "ListItem" else entry
            if not isinstance(product, dict):
                continue

            title = _clean_text(str(product.get("name") or ""))
            url = _clean_text(str(product.get("url") or ""))
            offers_node = product.get("offers")
            if isinstance(offers_node, list):
                offers_node = offers_node[0] if offers_node else None

            price_current = None
            price_list = None
            if isinstance(offers_node, dict):
                price_current = _extract_price(str(offers_node.get("price") or ""))
                price_list = _extract_price(str(offers_node.get("highPrice") or ""))

            if not title or not url or price_current is None:
                continue

            if not url.startswith("http"):
                url = urljoin(base_url, url)

            brand_value = product.get("brand")
            if isinstance(brand_value, dict):
                brand = _clean_text(str(brand_value.get("name") or ""))
            else:
                brand = _clean_text(str(brand_value or ""))
            if not brand:
                brand = title.split(" ")[0]

            offers.append(
                ProductOffer(
                    retailer_name="Cruz Verde",
                    retailer_domain="cruzverde.cl",
                    retailer_product_id=f"CV-{url.rstrip('/').split('/')[-1]}",
                    product_url=url,
                    title=title,
                    brand=brand,
                    size_raw=title,
                    category_raw="skincare",
                    price_current=price_current,
                    price_list=price_list,
                    promo_text=None,
                    in_stock=True,
                    scraped_at=now,
                )
            )
            if len(offers) >= max_items:
                return offers

    return offers


def _parse_from_html_heuristic(html: str, base_url: str, now: datetime, max_items: int) -> list[ProductOffer]:
    offers: list[ProductOffer] = []
    seen: set[str] = set()

    for href_match in _HREF_RE.finditer(html):
        href = href_match.group(1)
        url = urljoin(base_url, href)
        if url in seen:
            continue
        seen.add(url)

        start = max(0, href_match.start() - 350)
        end = min(len(html), href_match.end() + 350)
        window = html[start:end]

        title_match = _TITLE_RE.search(window)
        title = _clean_text(title_match.group(1) if title_match else "")
        if not title:
            slug = url.rstrip("/").split("/")[-1]
            title = _clean_text(slug.replace("-", " "))

        prices = [_extract_price(m.group(0)) for m in _PRICE_RE.finditer(window)]
        prices = [p for p in prices if p is not None and p > 0]
        if not prices:
            continue

        price_current = min(prices)
        price_list = max(prices) if len(prices) > 1 and max(prices) > min(prices) else None

        offers.append(
            ProductOffer(
                retailer_name="Cruz Verde",
                retailer_domain="cruzverde.cl",
                retailer_product_id=f"CV-{url.rstrip('/').split('/')[-1]}",
                product_url=url,
                title=title,
                brand=title.split(" ")[0] if title else "",
                size_raw=title,
                category_raw="skincare",
                price_current=price_current,
                price_list=price_list,
                promo_text=None,
                in_stock=True,
                scraped_at=now,
            )
        )
        if len(offers) >= max_items:
            break

    return offers


def collect_cruzverde_skincare(max_items: int = 100) -> list[ProductOffer]:
    start_url = os.getenv("CRUZVERDE_START_URL", DEFAULT_START_URL)
    max_pages = int(os.getenv("CRUZVERDE_MAX_PAGES", str(DEFAULT_MAX_PAGES)))
    now = datetime.now(timezone.utc)

    offers_by_id: dict[str, ProductOffer] = {}

    for page_url in _page_urls(start_url, max_pages):
        try:
            html = _fetch_html(page_url)
        except (HTTPError, URLError, TimeoutError, ValueError):
            continue

        page_offers = _parse_from_json_ld(html, page_url, now, max_items)
        if not page_offers:
            page_offers = _parse_from_html_heuristic(html, page_url, now, max_items)

        for offer in page_offers:
            offers_by_id[offer.retailer_product_id] = offer
            if len(offers_by_id) >= max_items:
                break

        if len(offers_by_id) >= max_items:
            break

    return list(offers_by_id.values())
