from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from html import unescape
from typing import Optional
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

from src.collectors.base import ProductOffer

DEFAULT_START_URL = "https://www.salcobrand.cl/cuidado-de-la-piel"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_MAX_PAGES = 3
DEFAULT_BROWSER_TIMEOUT_MS = 45000
DEFAULT_PARTNER_ID = "602bba6097a5281b4cc438c9"
DEFAULT_CATEGORY_PATH = "dermocoaching"

_PRICE_RE = re.compile(r"(\d{1,3}(?:[\.,]\d{3})+|\d+)")
_HREF_RE = re.compile(r"href=[\"']([^\"']+/(?:producto|productos|product|products)/[^\"']+)[\"']", re.IGNORECASE)
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


def _fetch_json(url: str) -> object:
    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; discount-detector/0.1)",
            "Accept": "application/json,text/plain,*/*",
            "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        },
    )
    with urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
        raw = resp.read().decode("utf-8", errors="ignore")
    return json.loads(raw)


def _collect_from_retailrocket_api(now: datetime, max_items: int) -> list[ProductOffer]:
    partner_id = os.getenv("SALCOBRAND_PARTNER_ID", DEFAULT_PARTNER_ID)
    configured = os.getenv("SALCOBRAND_CATEGORY_PATH", DEFAULT_CATEGORY_PATH).strip()
    candidate_paths = [
        configured,
        "cuidado-de-la-piel",
        "dermocosmetica",
        "dermocoaching",
        "",
    ]
    # Deduplicate while preserving order.
    seen_paths: set[str] = set()
    candidate_paths = [p for p in candidate_paths if not (p in seen_paths or seen_paths.add(p))]

    payload = []
    for category_path in candidate_paths:
        session = uuid.uuid4().hex[:24]
        pvid = str(abs(hash(f"{session}-{now.isoformat()}-{category_path}")) % 10**12)
        endpoint = (
            f"https://api.retailrocket.net/api/2.0/recommendation/popular/{partner_id}/"
            f"?categoryIds=&categoryPaths={category_path}&session={session}&pvid={pvid}&isDebug=false&format=json"
        )
        data = _fetch_json(endpoint)
        if isinstance(data, list) and data:
            payload = data
            break

    offers: list[ProductOffer] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        name = _clean_text(str(item.get("Name") or ""))
        url = _clean_text(str(item.get("Url") or ""))
        price_current = item.get("Price")
        old_price = item.get("OldPrice")
        if not name or not url or price_current is None:
            continue
        try:
            price_current = float(price_current)
        except Exception:
            continue
        try:
            price_list = float(old_price) if old_price is not None else None
        except Exception:
            price_list = None

        if not url.startswith("http"):
            url = urljoin("https://salcobrand.cl/", url)
        slug = url.rstrip("/").split("/")[-1] or uuid.uuid4().hex[:8]

        offers.append(
            ProductOffer(
                retailer_name="Salcobrand",
                retailer_domain="salcobrand.cl",
                retailer_product_id=f"SB-{slug}",
                product_url=url,
                title=name,
                brand=name.split(" ")[0] if name else "",
                size_raw=name,
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


def _fetch_html_playwright(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for Salcobrand rendering fallback. "
            "Install dependencies and browser: pip install -r requirements.txt && python -m playwright install chromium"
        ) from exc

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            )
            page.goto(url, wait_until="domcontentloaded", timeout=DEFAULT_BROWSER_TIMEOUT_MS)
            page.wait_for_timeout(3500)
            return page.content()
        finally:
            browser.close()


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
        urls.append(_add_or_replace_query(start_url, "p", str(page)))
        urls.append(_add_or_replace_query(start_url, "page", str(page)))

    # Keep insertion order, dedupe.
    deduped: list[str] = []
    seen: set[str] = set()
    for u in urls:
        if u in seen:
            continue
        seen.add(u)
        deduped.append(u)
    return deduped


def _parse_from_json_ld(html: str, base_url: str, now: datetime, max_items: int) -> list[ProductOffer]:
    def walk_nodes(node):
        if isinstance(node, dict):
            yield node
            for v in node.values():
                yield from walk_nodes(v)
        elif isinstance(node, list):
            for item in node:
                yield from walk_nodes(item)

    offers: list[ProductOffer] = []
    for match in _JSON_LD_RE.findall(html):
        raw = match.strip()
        if not raw:
            continue
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            continue

        for entry in walk_nodes(payload):
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
                    retailer_name="Salcobrand",
                    retailer_domain="salcobrand.cl",
                    retailer_product_id=f"SB-{url.rstrip('/').split('/')[-1]}",
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
                retailer_name="Salcobrand",
                retailer_domain="salcobrand.cl",
                retailer_product_id=f"SB-{url.rstrip('/').split('/')[-1]}",
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


def collect_salcobrand_skincare(max_items: int = 100) -> list[ProductOffer]:
    start_url = os.getenv("SALCOBRAND_START_URL", DEFAULT_START_URL)
    max_pages = int(os.getenv("SALCOBRAND_MAX_PAGES", str(DEFAULT_MAX_PAGES)))
    now = datetime.now(timezone.utc)

    # Prefer direct product API discovered via network capture.
    try:
        api_offers = _collect_from_retailrocket_api(now, max_items)
        if api_offers:
            return api_offers
    except Exception:
        pass

    offers_by_id: dict[str, ProductOffer] = {}
    page_errors: list[str] = []
    render_errors: list[str] = []
    fetched_pages = 0
    use_playwright = os.getenv("SALCOBRAND_USE_PLAYWRIGHT", "1").lower() not in {"0", "false", "no"}
    for page_url in _page_urls(start_url, max_pages):
        try:
            html = _fetch_html(page_url)
        except (HTTPError, URLError, TimeoutError, ValueError):
            page_errors.append(page_url)
            continue
        fetched_pages += 1

        page_offers = _parse_from_json_ld(html, page_url, now, max_items)
        if not page_offers:
            page_offers = _parse_from_html_heuristic(html, page_url, now, max_items)
        if not page_offers and use_playwright:
            try:
                rendered_html = _fetch_html_playwright(page_url)
                page_offers = _parse_from_json_ld(rendered_html, page_url, now, max_items)
                if not page_offers:
                    page_offers = _parse_from_html_heuristic(rendered_html, page_url, now, max_items)
            except Exception as exc:  # pragma: no cover
                render_errors.append(f"{page_url}: {exc}")

        for offer in page_offers:
            offers_by_id[offer.retailer_product_id] = offer
            if len(offers_by_id) >= max_items:
                break

        if len(offers_by_id) >= max_items:
            break

    if fetched_pages == 0:
        raise RuntimeError(
            f"Could not fetch any Salcobrand pages (start_url={start_url}, pages={max_pages}). "
            f"Failed URLs: {', '.join(page_errors[:3])}"
        )
    if not offers_by_id:
        render_part = f" Render errors: {' | '.join(render_errors[:2])}" if render_errors else ""
        raise RuntimeError(
            f"Fetched {fetched_pages} Salcobrand page(s) but parsed 0 offers. "
            f"Selectors/markup likely changed.{render_part}"
        )
    return list(offers_by_id.values())
