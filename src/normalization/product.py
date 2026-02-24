from __future__ import annotations

import re

_SIZE_RE = re.compile(r"(?P<value>\d+(?:[\.,]\d+)?)\s*(?P<unit>ml|g|kg|l|un)", re.IGNORECASE)


def normalize_text(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def parse_size(size_raw: str) -> tuple[float | None, str | None]:
    match = _SIZE_RE.search(size_raw or "")
    if not match:
        return None, None
    raw_value = match.group("value").replace(",", ".")
    return float(raw_value), match.group("unit").lower()


def canonical_key(brand: str, title: str, size_raw: str) -> tuple[str, str, float | None, str | None]:
    size_value, size_unit = parse_size(size_raw)
    return normalize_text(brand), normalize_text(title), size_value, size_unit
