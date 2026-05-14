from __future__ import annotations

import logging
import os
from typing import List

from src.models.product import Product, PlatformCode
from src.tools.crawler.base import BaseCrawler
from src.tools.crawler.mock import MockCrawler

logger = logging.getLogger(__name__)


def _get_crawler(platform: PlatformCode) -> BaseCrawler:
    if platform == "jd":
        enabled = os.getenv("JD_OPEN_PLATFORM_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
        if enabled:
            try:
                from src.tools.crawler.JD import JdOpenPlatformCrawler

                crawler = JdOpenPlatformCrawler.from_env()
                if crawler is not None:
                    return crawler
            except Exception as exc:
                logger.warning("JD crawler init failed, fallback mock: %s", exc)
    return MockCrawler()


def _dedupe_products(products: List[Product]) -> List[Product]:
    seen_ids: set[str] = set()
    deduped: list[Product] = []
    for product in products:
        if product.id in seen_ids:
            continue
        seen_ids.add(product.id)
        deduped.append(product)
    return deduped


def _search_jd_via_research(query: str, limit: int) -> List[Product]:
    try:
        from src.agents.common.toolkits.research.tools import search_products

        result = search_products.invoke({"keyword": query, "page": 1, "need_price": True})
        products = result.get("products") or []
        error = result.get("error")
        if error:
            logger.info("research search fallback triggered: %s", error)
        jd_products = [p for p in products if isinstance(p, Product) and p.platform == "jd"]
        return _dedupe_products(jd_products)[:limit]
    except Exception as exc:
        logger.warning("research search failed, fallback crawler: %s", exc)
        return []


def _search_via_crawlers(query: str, platforms: List[PlatformCode], limit: int) -> List[Product]:
    results: list[Product] = []
    fetch_limit = max(limit, 100)
    for platform in platforms:
        crawler = _get_crawler(platform)
        platform_results = crawler.search(query, limit=fetch_limit)
        filtered = [p for p in platform_results if p.platform == platform]
        results.extend(filtered[:limit])
    return _dedupe_products(results)


def search_products_gateway(
    query: str,
    platforms: List[PlatformCode],
    limit: int,
) -> List[Product]:
    results: list[Product] = []
    fallback_platforms: list[PlatformCode] = []

    for platform in platforms:
        if platform != "jd":
            fallback_platforms.append(platform)
            continue

        jd_products = _search_jd_via_research(query, limit)
        if jd_products:
            results.extend(jd_products)
        else:
            fallback_platforms.append(platform)

    if fallback_platforms:
        results.extend(_search_via_crawlers(query, fallback_platforms, limit))

    return _dedupe_products(results)
