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
DEFAULT_BROWSER_TIMEOUT_MS = 45000
DEFAULT_API_BASE_URL = "https://api.cruzverde.cl/product-service"
DEFAULT_API_PAGE_SIZE = 24
DEFAULT_MAX_CATEGORY_PAGES = 5
DEFAULT_AUTH_URL = "https://profiles-orc.api.andesml.com/identity/v1/client/auth"
DEFAULT_AUTH_CLIENT_ID = "GxkRx0Db/VacheHZPWA4LlE8J09E3SX+aQblEE7pLn2NA7X9uU7eNYe/2oMnlLNKPPPTYV6IatroV59//yYeEw=="
DEFAULT_AUTH_CLIENT_SECRET = "0udIUHRl0FDKzzIlYsgsHsgs9ltoMr89j5gjlWpZetbRhmLNeq7qBiv+CnnnPS5BYwmsZqtj8Z8xE3vA"

_PRICE_RE = re.compile(r"(\d{1,3}(?:[\.,]\d{3})+|\d+)")
_HREF_RE = re.compile(r"href=[\"']([^\"']+/(?:producto|productos|product|products|p)/[^\"']+)[\"']", re.IGNORECASE)
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


def _fetch_json(url: str, headers: Optional[dict[str, str]] = None) -> object:
    request_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; discount-detector/0.1)",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
    }
    if headers:
        request_headers.update(headers)
    req = Request(
        url,
        headers=request_headers,
    )
    with urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _post_json(url: str, payload: dict[str, str], headers: Optional[dict[str, str]] = None) -> object:
    request_headers = {
        "User-Agent": "Mozilla/5.0 (compatible; discount-detector/0.1)",
        "Accept": "application/json,text/plain,*/*",
        "Accept-Language": "es-CL,es;q=0.9,en;q=0.8",
        "Content-Type": "application/json",
    }
    if headers:
        request_headers.update(headers)
    body = json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, headers=request_headers, method="POST")
    with urlopen(req, timeout=DEFAULT_TIMEOUT_SECONDS) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def _fetch_access_token() -> Optional[str]:
    auth_url = os.getenv("CRUZVERDE_AUTH_URL", DEFAULT_AUTH_URL).strip()
    client_id = os.getenv("CRUZVERDE_AUTH_CLIENT_ID", DEFAULT_AUTH_CLIENT_ID).strip()
    client_secret = os.getenv("CRUZVERDE_AUTH_CLIENT_SECRET", DEFAULT_AUTH_CLIENT_SECRET).strip()
    if not auth_url or not client_id or not client_secret:
        return None

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "grant_type": "client_credentials",
        "scope": "openid",
    }
    data = _post_json(auth_url, payload)
    if not isinstance(data, dict):
        return None
    auth_data = data.get("auth_data")
    if not isinstance(auth_data, dict):
        return None
    token = auth_data.get("access_token")
    if not isinstance(token, str) or not token.strip():
        return None
    return token.strip()


def _fetch_html_playwright(url: str) -> str:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright is required for Cruz Verde SPA rendering. "
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
            # Let product cards render in SPA pages.
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


def _iter_category_nodes(node):
    if isinstance(node, dict):
        yield node
        categories = node.get("categories")
        if isinstance(categories, list):
            for child in categories:
                yield from _iter_category_nodes(child)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_category_nodes(item)


def _is_skincare_category(category: dict) -> bool:
    path = _clean_text(str(category.get("path") or "")).lower()
    slug = _clean_text(str(category.get("slug") or "")).lower()
    cat_id = _clean_text(str(category.get("id") or "")).lower()
    if path.startswith("/dermocosmetica/") or path.startswith("/cuidado-piel/"):
        return True
    if "dermocosmetica" in cat_id or "dermocosmetica" in slug:
        return True
    return False


def _candidate_category_ids() -> list[str]:
    configured = os.getenv("CRUZVERDE_CATEGORY_IDS", "").strip()
    defaults = [
        "dermocosmetica",
        "rostro-dermocosmetica",
        "cuidado-piel-proteccion-solar",
        "dermocosmetica-vichy",
        "dermocosmetica-la-roche-posay",
        "dermocosmetica-eucerin",
        "dermocosmetica-avene",
        "dermocosmetica-bioderma",
        "dermocosmetica-uriage",
        "dermocosmetica-isdin",
    ]
    seeds = [x.strip() for x in configured.split(",") if x.strip()] if configured else defaults
    deduped: list[str] = []
    seen: set[str] = set()
    for cid in seeds:
        if cid in seen:
            continue
        seen.add(cid)
        deduped.append(cid)
    return deduped


def _parse_price(value) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except Exception:
        return _extract_price(str(value))


def _collect_from_products_api(now: datetime, max_items: int) -> list[ProductOffer]:
    api_base = os.getenv("CRUZVERDE_API_BASE_URL", DEFAULT_API_BASE_URL).rstrip("/")
    page_size = int(os.getenv("CRUZVERDE_API_PAGE_SIZE", str(DEFAULT_API_PAGE_SIZE)))
    max_category_pages = int(os.getenv("CRUZVERDE_MAX_CATEGORY_PAGES", str(DEFAULT_MAX_CATEGORY_PAGES)))

    access_token = _fetch_access_token()
    api_headers: dict[str, str] = {
        "Origin": "https://www.cruzverde.cl",
        "Referer": "https://www.cruzverde.cl/",
    }
    if access_token:
        api_headers["Authorization"] = f"Bearer {access_token}"

    category_ids = _candidate_category_ids()
    dynamic_ids: list[str] = []
    try:
        tree_url = f"{api_base}/categories/category-tree?showInMenu=true"
        tree_payload = _fetch_json(tree_url, headers=api_headers)
        for node in _iter_category_nodes(tree_payload):
            if not isinstance(node, dict):
                continue
            if not _is_skincare_category(node):
                continue
            cid = _clean_text(str(node.get("id") or ""))
            if cid:
                dynamic_ids.append(cid)
    except Exception:
        # Keep configured defaults if tree endpoint changes or becomes unavailable.
        pass

    all_category_ids: list[str] = []
    seen_ids: set[str] = set()
    for cid in category_ids + dynamic_ids:
        if not cid or cid in seen_ids:
            continue
        seen_ids.add(cid)
        all_category_ids.append(cid)

    offers_by_id: dict[str, ProductOffer] = {}
    any_success = False
    last_error: Optional[str] = None

    for category_id in all_category_ids:
        for page_idx in range(max_category_pages):
            offset = page_idx * page_size
            query = urlencode(
                {
                    "limit": str(page_size),
                    "offset": str(offset),
                    "sort": "",
                    "q": "",
                    "isAndes": "true",
                }
            )
            search_url = (
                f"{api_base}/products/search?{query}"
                f"&refine%5B%5D=cgid%3D{category_id}"
            )

            payload = None
            for auth_attempt in range(2):
                try:
                    payload = _fetch_json(search_url, headers=api_headers)
                    break
                except HTTPError as exc:
                    last_error = f"{category_id}@{offset}: {exc}"
                    if exc.code == 401 and auth_attempt == 0:
                        access_token = _fetch_access_token()
                        if access_token:
                            api_headers["Authorization"] = f"Bearer {access_token}"
                            continue
                    break
                except Exception as exc:
                    last_error = f"{category_id}@{offset}: {exc}"
                    break
            if payload is None:
                break

            if not isinstance(payload, dict):
                continue
            any_success = True
            hits = payload.get("hits")
            if not isinstance(hits, list) or not hits:
                break

            for hit in hits:
                if not isinstance(hit, dict):
                    continue
                product_id = _clean_text(str(hit.get("productId") or ""))
                title = _clean_text(str(hit.get("productName") or ""))
                if not product_id or not title:
                    continue

                prices = hit.get("prices") if isinstance(hit.get("prices"), dict) else {}
                price_current = _parse_price(
                    prices.get("price-sale-cl") if isinstance(prices, dict) else None
                )
                price_list = _parse_price(
                    prices.get("price-list-cl") if isinstance(prices, dict) else None
                )
                if price_current is None:
                    price_current = price_list
                if price_current is None:
                    continue

                product_url = _clean_text(str(hit.get("link") or ""))
                if not product_url:
                    product_url = f"https://www.cruzverde.cl/producto/{product_id}"

                brand = _clean_text(str(hit.get("brand") or "")) or title.split(" ")[0]

                promo_text = None
                applied = hit.get("appliedPromotions")
                if isinstance(applied, dict):
                    applied_sale = applied.get("price-sale-cl")
                    if isinstance(applied_sale, dict):
                        promo_text = _clean_text(str(applied_sale.get("calloutMsg") or ""))
                if not promo_text and isinstance(hit.get("promotions"), list) and hit["promotions"]:
                    first_promo = hit["promotions"][0]
                    if isinstance(first_promo, dict):
                        promo_text = _clean_text(str(first_promo.get("calloutMsg") or ""))
                if not promo_text:
                    promo_text = None

                offer = ProductOffer(
                    retailer_name="Cruz Verde",
                    retailer_domain="cruzverde.cl",
                    retailer_product_id=f"CV-{product_id}",
                    product_url=product_url,
                    title=title,
                    brand=brand,
                    size_raw=title,
                    category_raw="skincare",
                    price_current=price_current,
                    price_list=price_list,
                    promo_text=promo_text,
                    in_stock=True,
                    scraped_at=now,
                )
                offers_by_id[offer.retailer_product_id] = offer
                if len(offers_by_id) >= max_items:
                    return list(offers_by_id.values())

            total_count = payload.get("count")
            if isinstance(total_count, int) and offset + page_size >= total_count:
                break

    if not offers_by_id and not any_success and last_error:
        raise RuntimeError(f"Cruz Verde products API unavailable: {last_error}")
    return list(offers_by_id.values())


def collect_cruzverde_skincare(max_items: int = 100) -> list[ProductOffer]:
    start_url = os.getenv("CRUZVERDE_START_URL", DEFAULT_START_URL)
    max_pages = int(os.getenv("CRUZVERDE_MAX_PAGES", str(DEFAULT_MAX_PAGES)))
    now = datetime.now(timezone.utc)

    offers_by_id: dict[str, ProductOffer] = {}
    page_errors: list[str] = []
    render_errors: list[str] = []
    fetched_pages = 0
    use_playwright = os.getenv("CRUZVERDE_USE_PLAYWRIGHT", "1").lower() not in {"0", "false", "no"}
    api_error: Optional[str] = None

    try:
        api_offers = _collect_from_products_api(now, max_items)
        if api_offers:
            return api_offers
    except Exception as exc:
        api_error = str(exc)

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
        if not page_offers and use_playwright and "<app-root" in html:
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
        api_part = f" API error: {api_error}" if api_error else ""
        raise RuntimeError(
            f"Could not fetch any Cruz Verde pages (start_url={start_url}, pages={max_pages}). "
            f"Failed URLs: {', '.join(page_errors[:3])}.{api_part}"
        )
    if not offers_by_id:
        render_part = f" Render errors: {' | '.join(render_errors[:2])}" if render_errors else ""
        api_part = f" API error: {api_error}" if api_error else ""
        raise RuntimeError(
            f"Fetched {fetched_pages} Cruz Verde page(s) but parsed 0 offers. "
            f"Selectors/markup likely changed.{render_part}{api_part}"
        )
    return list(offers_by_id.values())
