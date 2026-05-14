from __future__ import annotations

import os
from typing import Any, List

from src.models.product import Product
from src.tools.crawler.base import BaseCrawler
from src.tools.crawler.jd_open_platform_client import JdOpenPlatformClient


class JdOpenPlatformCrawler(BaseCrawler):
    def __init__(
        self,
        *,
        app_key: str,
        app_secret: str,
        access_token: str | None = None,
        base_url: str | None = None,
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        self.access_token = access_token
        self.base_url = base_url

    @classmethod
    def from_env(cls) -> "JdOpenPlatformCrawler | None":
        app_key = (os.getenv("JD_OPEN_PLATFORM_APP_KEY") or "").strip()
        app_secret = (os.getenv("JD_OPEN_PLATFORM_APP_SECRET") or "").strip()
        if not app_key or not app_secret:
            return None
        access_token = (os.getenv("JD_OPEN_PLATFORM_ACCESS_TOKEN") or "").strip() or None
        base_url = (os.getenv("JD_OPEN_PLATFORM_BASE_URL") or "").strip() or None
        return cls(app_key=app_key, app_secret=app_secret, access_token=access_token, base_url=base_url)

    @staticmethod
    def map_item_to_product(item: dict[str, Any]) -> Product:
        sku = item.get("skuId") or item.get("sku_id") or item.get("id") or item.get("sku")
        if sku is None:
            raise ValueError("JD item missing skuId")
        sku_str = str(sku).strip()
        title = item.get("skuName") or item.get("title") or item.get("name")
        if title is None:
            raise ValueError("JD item missing skuName")
        title_str = str(title).strip()
        if not title_str:
            raise ValueError("JD item empty skuName")

        price_raw = item.get("price") or item.get("jdPrice") or item.get("p")
        if price_raw is None:
            raise ValueError("JD item missing price")
        try:
            price = float(price_raw)
        except Exception:
            raise ValueError("JD item invalid price")
        if price <= 0:
            raise ValueError("JD item invalid price")
        url = item.get("url") or item.get("detailUrl") or item.get("materialUrl") or f"https://item.jd.com/{sku_str}.html"
        image_url = item.get("imageUrl") or item.get("img") or item.get("image") or None
        brand = item.get("brandName") or item.get("brand") or None
        return Product(
            id=f"jd_{sku_str}",
            title=title_str,
            price=price,
            state=1,
            platform="jd",
            url=url,
            image_url=image_url,
            brand=brand,
        )

    @staticmethod
    def _extract_items(data: Any) -> list[dict[str, Any]]:
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if not isinstance(data, dict):
            return []
        for key in ("items", "itemList", "skuList", "data", "result", "list"):
            v = data.get(key)
            if isinstance(v, list):
                return [x for x in v if isinstance(x, dict)]
            if isinstance(v, dict):
                for k in ("items", "list", "skuList"):
                    vv = v.get(k)
                    if isinstance(vv, list):
                        return [x for x in vv if isinstance(x, dict)]
        return []

    def search(self, query: str, limit: int = 10) -> List[Product]:
        query = str(query).strip()
        if not query:
            raise ValueError("query must not be empty")
        if limit <= 0:
            return []

        endpoint = (os.getenv("JD_OPEN_PLATFORM_SEARCH_ENDPOINT") or "").strip()
        client = JdOpenPlatformClient.from_env(
            base_url=(self.base_url or "").strip(),
            endpoint=endpoint,
            app_key=self.app_key,
            app_secret=self.app_secret,
            access_token=self.access_token,
        )
        data = client.call(query=query, limit=int(limit))
        items = self._extract_items(data)
        products: list[Product] = []
        for item in items[: int(limit)]:
            try:
                products.append(self.map_item_to_product(item))
            except Exception:
                continue
        return products
