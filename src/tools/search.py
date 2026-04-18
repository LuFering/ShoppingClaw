from __future__ import annotations

from typing import List

from src.models.product import Product, PlatformCode
from src.tools.crawler.base import BaseCrawler
from src.tools.crawler.mock import MockCrawler

ALL_PLATFORMS: List[PlatformCode] = ["jd", "taobao", "pdd"]


def _get_crawler(platform: PlatformCode) -> BaseCrawler:
    # #  MVP 阶段统一使用 MockCrawler，真实爬虫接入后按 platform 分发   暂时好像是platform的
    # _ =platform
    return MockCrawler()


def _normalize_platforms(platforms: List[PlatformCode] | None) -> List[PlatformCode]:
    if platforms is None:
        return list(ALL_PLATFORMS)
    # if len(platforms) == 0:
    #     return []
    # return list(platforms)
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


def search(
    query: str,
    platforms: List[PlatformCode] | None = None,
    limit: int = 10,
) -> List[Product]:
    """
    搜索商品（按平台聚合）。

    Args:
        query: 用户搜索词，不能为空或全空格，长度不超过 100。
        platforms: 平台列表，为 None 表示全平台，为 [] 表示不搜索任何平台。
        limit: 每个平台返回的商品数量（1-100）。

    Returns:
        商品列表（List[Product]），按平台结果顺序拼接。

    Raises:
        ValueError: query 为空/超长，或 limit 超出范围。

    Examples:
        >>> items = search("iphone 15", platforms=["jd"], limit=5)
        >>> len(items) >= 1
        True
    """
    normalized_query = _validate_query(query)
    _validate_limit(limit)
    selected_platforms = _normalize_platforms(platforms)
    if not selected_platforms:
        return []

    results: List[Product] = []
    for platform in selected_platforms:
        crawler = _get_crawler(platform)
        platform_results = crawler.search(normalized_query, limit=limit)
        # 防御：MockCrawler 可能返回多平台数据，确保只保留当前平台结果
        filtered = [p for p in platform_results if p.platform == platform]
        results.extend(filtered[:limit])

    return results
