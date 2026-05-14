from __future__ import annotations

import logging
from typing import List

from src.models.product import Product, PlatformCode
from src.tools.search_gateway import search_products_gateway

logger = logging.getLogger(__name__)

ALL_PLATFORMS: List[PlatformCode] = ["jd", "taobao", "pdd"]


def _normalize_platforms(platforms: List[PlatformCode] | None) -> List[PlatformCode]:
    if platforms is None:
        return list(ALL_PLATFORMS)
    return list(platforms)


def _validate_query(query: str) -> str:
    stripped = query.strip()
    if not stripped:
        raise ValueError("query must not be empty")
    if len(stripped) > 100:
        raise ValueError("query length must be <= 100")
    return stripped


def _validate_limit(limit: int) -> int:
    if limit <= 0 or limit > 100:
        raise ValueError("limit must be between 1 and 100")
    return limit


def search(query: str, platforms: List[PlatformCode] | None = None, limit: int = 10) -> List[Product]:
    normalized_query = _validate_query(query)
    validated_limit = _validate_limit(limit)
    selected_platforms = _normalize_platforms(platforms)
    if not selected_platforms:
        return []
    logger.info("search.gateway query=%s platforms=%s limit=%s", normalized_query, selected_platforms, validated_limit)
    return search_products_gateway(
        query=normalized_query,
        platforms=selected_platforms,
        limit=validated_limit,
    )
