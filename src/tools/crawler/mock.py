from __future__ import annotations

from typing import List

from src.models.product import Product
from src.tools.crawler.base import BaseCrawler


class MockCrawler(BaseCrawler):
    """Mock 爬虫：返回固定假数据，用于开发与测试。"""

    def search(self, query: str, limit: int = 10) -> List[Product]:
        """
        搜索商品（Mock 阶段不使用 query）。
        ... query 当前阶段未使用，保留以对齐接口契约

        Args:
            query: 搜索关键词（当前不参与逻辑）
            limit: 返回数量上限

        Returns:
            Product 列表（固定 3 条，但会按 limit 截断）
        """
        _ = query  # 明确表示当前阶段不使用 query 参数

        fixed_products = [
            Product(
                id="jd_mock_001",
                title="Apple iPhone 15 Pro 256GB 黑色钛金属",
                price=8999.0,
                platform="jd",
                url="https://mock.com/item/001",
                image_url="https://mock.com/image/001.jpg",
                shop_name="Mock官方旗舰店",
                rating=4.8,
                comment_count=10000,
                sales_count=50000,
                category="手机",
                brand="Apple",
                specs={"内存": "256GB", "颜色": "黑色", "网络": "5G"},
            ),
            Product(
                id="jd_mock_002",
                title="Apple iPhone 15 Pro Max 512GB 原色钛金属",
                price=10999.0,
                platform="jd",
                url="https://mock.com/item/002",
                image_url="https://mock.com/image/002.jpg",
                shop_name="Mock官方旗舰店",
                rating=4.9,
                comment_count=20000,
                sales_count=80000,
                category="手机",
                brand="Apple",
                specs={"内存": "512GB", "颜色": "原色", "网络": "5G"},
            ),
            Product(
                id="jd_mock_003",
                title="小米 14 12GB+256GB 黑色",
                price=3999.0,
                platform="jd",
                url="https://mock.com/item/003",
                image_url="https://mock.com/image/003.jpg",
                shop_name="小米京东自营旗舰店",
                rating=4.6,
                comment_count=5000,
                sales_count=20000,
                category="手机",
                brand="小米",
                specs={"内存": "12GB", "存储": "256GB", "颜色": "黑色"},
            ),
            Product(
                id="taobao_mock_001",
                title="小米 14 Pro 16GB+512GB 黑色",
                price=4999.0,
                platform="taobao",
                url="https://mock.com/item/004",
                image_url="https://mock.com/image/004.jpg",
                shop_name="小米官方旗舰店（Mock）",
                rating=4.7,
                comment_count=8000,
                sales_count=30000,
                category="手机",
                brand="小米",
                specs={"内存": "16GB", "存储": "512GB", "颜色": "黑色"},
            ),
            Product(
                id="taobao_mock_002",
                title="华为 Mate 60 12GB+512GB 雅丹黑",
                price=5999.0,
                platform="taobao",
                url="https://mock.com/item/005",
                image_url="https://mock.com/image/005.jpg",
                shop_name="华为官方旗舰店（Mock）",
                rating=4.8,
                comment_count=9000,
                sales_count=35000,
                category="手机",
                brand="华为",
                specs={"内存": "12GB", "存储": "512GB", "颜色": "雅丹黑"},
            ),
            Product(
                id="taobao_mock_003",
                title="Apple iPhone 15 128GB 粉色",
                price=5999.0,
                platform="taobao",
                url="https://mock.com/item/006",
                image_url="https://mock.com/image/006.jpg",
                shop_name="Apple Store 官方旗舰店",
                rating=4.7,
                comment_count=15000,
                sales_count=60000,
                category="手机",
                brand="Apple",
                specs={"内存": "128GB", "颜色": "粉色", "网络": "5G"},
            ),
            Product(
                id="pdd_mock_001",
                title="华为 Mate 60 Pro 12GB+256GB 雅川青",
                price=6999.0,
                platform="pdd",
                url="https://mock.com/item/007",
                image_url="https://mock.com/image/007.jpg",
                shop_name="华为官方旗舰店（Mock）",
                rating=4.9,
                comment_count=12000,
                sales_count=40000,
                category="手机",
                brand="华为",
                specs={"内存": "12GB", "存储": "256GB", "颜色": "雅川青"},
            ),
            Product(
                id="pdd_mock_002",
                title="百亿补贴：Apple iPhone 15 Pro 256GB",
                price=7999.0,
                platform="pdd",
                url="https://mock.com/item/008",
                image_url="https://mock.com/image/008.jpg",
                shop_name="拼多多苹果品牌店",
                rating=4.5,
                comment_count=30000,
                sales_count=100000,
                category="手机",
                brand="Apple",
                specs={"内存": "256GB", "颜色": "随机", "网络": "5G"},
            ),
            Product(
                id="pdd_mock_003",
                title="百亿补贴：小米 14 16GB+512GB",
                price=4299.0,
                platform="pdd",
                url="https://mock.com/item/009",
                image_url="https://mock.com/image/009.jpg",
                shop_name="拼多多小米品牌店",
                rating=4.6,
                comment_count=10000,
                sales_count=45000,
                category="手机",
                brand="小米",
                specs={"内存": "16GB", "存储": "512GB", "颜色": "随机"},
            ),
        ]

        # 保持接口预测性：limit<=0 时返回空列表；limit>=3 时返回完整 3 条
        if limit <= 0:
            return []
        return fixed_products[:limit]

