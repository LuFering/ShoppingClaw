from __future__ import annotations

from typing import List, Optional

from src.models.product import Product, PlatformCode


def _safe_positive_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def filter_products(
    products: List[Product],
    *,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    platforms: Optional[List[PlatformCode]] = None,
    min_rating: Optional[float] = None,
    brands: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
) -> List[Product]:
    if not products:
        return []

    if price_min is not None and price_max is not None and price_min > price_max:
        raise ValueError("price_min不能大于price_max")

    if min_rating is not None and (min_rating < 0 or min_rating > 5):
        raise ValueError("min_rating必须在0-5之间")

    filtered = products

    if price_min is not None:
        filtered = [p for p in filtered if (price := _safe_positive_float(p.price)) is not None and price >= price_min]
    if price_max is not None:
        filtered = [p for p in filtered if (price := _safe_positive_float(p.price)) is not None and price <= price_max]

    if platforms is not None:
        allowed = set(platforms)
        filtered = [p for p in filtered if p.platform in allowed]

    if min_rating is not None:
        filtered = [p for p in filtered if (p.rating or 0) >= min_rating]

    if brands:
        allowed_brands = set(b.lower() for b in brands)
        filtered = [p for p in filtered if (p.brand or "").lower() in allowed_brands]

    if keywords:
        keys = [k.lower() for k in keywords]
        filtered = [p for p in filtered if any(k in (p.title or "").lower() for k in keys)]

    return filtered
