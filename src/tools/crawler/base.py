from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List

from src.models.product import Product


class BaseCrawler(ABC):
    @abstractmethod
    def search(self, query: str, limit: int = 10) -> List[Product]:
        raise NotImplementedError

