from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from src.models.product import Product


class BaseCrawler(ABC):
    """爬虫基类：所有平台爬虫都必须继承此类并实现 `search`。"""

    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[Product]:
        """
        搜索商品

        Args:
            query: 搜索关键词
            limit: 返回商品数量限制

        Returns:
            商品列表（统一返回 `List[Product]` 以便后续节点消费）
        """
        raise NotImplementedError

