from __future__ import annotations

import os
import re
import urllib.request
from urllib.error import URLError, HTTPError

TARGETS = {
    "salcobrand": os.getenv("SALCOBRAND_START_URL", "https://www.salcobrand.cl/cuidado-de-la-piel"),
    "cruzverde": os.getenv("CRUZVERDE_START_URL", "https://www.cruzverde.cl/cuidado-facial"),
    "falabella": os.getenv(
        "FALABELLA_START_URL", "https://www.falabella.com/falabella-cl/category/cat2060/Cuidado-de-la-piel"
    ),
}

JSONLD_RE = re.compile(r'<script[^>]*type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.I | re.S)
PROD_LINK_RE = re.compile(r'href=["\']([^"\']+/(?:producto|productos|product|products|p)/[^"\']+)["\']', re.I)
PRICE_RE = re.compile(r'(?:\$|CLP|Precio|price)[^\d]{0,8}(\d{1,3}(?:[\.,]\d{3})+|\d+)', re.I)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.read().decode("utf-8", errors="ignore")


def main() -> None:
    for name, url in TARGETS.items():
        print(f"--- {name} ---")
        print("url:", url)
        try:
            html = fetch(url)
        except (HTTPError, URLError, TimeoutError, ValueError) as exc:
            print("fetch_error:", repr(exc))
            continue

        jsonld_count = len(JSONLD_RE.findall(html))
        links = PROD_LINK_RE.findall(html)
        prices = PRICE_RE.findall(html)

        print("html_len:", len(html))
        print("jsonld_count:", jsonld_count)
        print("product_link_count:", len(links))
        print("price_hint_count:", len(prices))

        preview_links = links[:5]
        if preview_links:
            print("product_link_preview:")
            for ln in preview_links:
                print(" ", ln)

        out_file = f"data/{name}_debug_sample.html"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(html)
        print("saved_html:", out_file)


if __name__ == "__main__":
    main()
