from __future__ import annotations

from typing import List

from src.models.product import Product
from src.tools.crawler.base import BaseCrawler


class MockCrawler(BaseCrawler):
    def search(self, query: str, limit: int = 10) -> List[Product]:
        _ = query
        products = [
            Product(
                id="jd_mock_001",
                title="Apple iPhone 15 Pro 256GB",
                price=8999.0,
                state=1,
                platform="jd",
                url="https://mock.com/item/001",
            ),
            Product(
                id="taobao_mock_001",
                title="Apple iPhone 15 128GB 粉色",
                price=5999.0,
                state=1,
                platform="taobao",
                url="https://mock.com/item/002",
            ),
            Product(
                id="pdd_mock_001",
                title="百亿补贴：Apple iPhone 15 Pro 256GB",
                price=7999.0,
                state=1,
                platform="pdd",
                url="https://mock.com/item/003",
            ),
        ]
        if limit <= 0:
            return []
        return products[:limit]

