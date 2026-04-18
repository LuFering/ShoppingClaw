import pytest
from src.tools.filter import filter_products
from src.models.product import Product


class TestFilterTool:
    """过滤工具测试类"""
    
    def test_filter_by_price_range(self):
        """测试价格范围过滤"""
        products = [
            Product(id="1", title="商品1", price=1000, platform="jd", url="https://example.com/item/1"),
            Product(id="2", title="商品2", price=2000, platform="jd", url="https://example.com/item/2"),
            Product(id="3", title="商品3", price=3000, platform="jd", url="https://example.com/item/3"),
        ]
        filtered = filter_products(products, price_min=1500, price_max=2500)
        assert len(filtered) == 1
        assert filtered[0].id == "2"
    
    def test_filter_by_platform(self):
        """测试平台过滤"""
        products = [
            Product(id="1", title="商品1", price=1000, platform="jd", url="https://example.com/item/1"),
            Product(id="2", title="商品2", price=1000, platform="taobao", url="https://example.com/item/2"),
            Product(id="3", title="商品3", price=1000, platform="pdd", url="https://example.com/item/3"),
        ]
        filtered = filter_products(products, platforms=["jd", "taobao"])
        assert len(filtered) == 2
        assert all(p.platform in ["jd", "taobao"] for p in filtered)
    
    def test_filter_by_rating(self):
        """测试评分过滤"""
        products = [
            Product(id="1", title="商品1", price=1000, platform="jd", url="https://example.com/item/1", rating=4.0),
            Product(id="2", title="商品2", price=1000, platform="jd", url="https://example.com/item/2", rating=4.5),
            Product(id="3", title="商品3", price=1000, platform="jd", url="https://example.com/item/3", rating=3.5),
        ]
        filtered = filter_products(products, min_rating=4.0)
        assert len(filtered) == 2
        assert all(p.rating >= 4.0 for p in filtered)
    
    def test_filter_by_brand(self):
        """测试品牌过滤"""
        products = [
            Product(id="1", title="iPhone 15", price=1000, platform="jd", url="https://example.com/item/1", brand="Apple"),
            Product(id="2", title="小米14", price=1000, platform="jd", url="https://example.com/item/2", brand="小米"),
            Product(id="3", title="华为Mate 60", price=1000, platform="jd", url="https://example.com/item/3", brand="华为"),
        ]
        filtered = filter_products(products, brands=["Apple", "小米"])
        assert len(filtered) == 2
        assert all(p.brand in ["Apple", "小米"] for p in filtered)
    
    def test_filter_combined_conditions(self):
        """测试组合条件过滤"""
        products = [
            Product(id="1", title="iPhone 15", price=8000, platform="jd", url="https://example.com/item/1", brand="Apple", rating=4.8),
            Product(id="2", title="iPhone 15", price=9000, platform="taobao", url="https://example.com/item/2", brand="Apple", rating=4.5),
            Product(id="3", title="小米14", price=4000, platform="jd", url="https://example.com/item/3", brand="小米", rating=4.7),
        ]
        filtered = filter_products(
            products,
            price_min=5000,
            price_max=10000,
            brands=["Apple"],
            min_rating=4.5
        )
        assert len(filtered) == 2
        # 现在： 条件是否 条件是否生效
        
        # Optimized by Claude
        assert all(
            p.brand == "Apple"
            and 5000 <= p.price <= 10000
            and p.rating >= 4.5
            for p in filtered
        )
        # assert all(p.brand == "Apple" and p.price >= 5000 and p.price <= 10000 for p in filtered)
    
    def test_filter_empty_result(self):
        """测试无符合条件结果"""
        products = [
            Product(id="1", title="商品1", price=1000, platform="jd", url="https://example.com/item/1"),
            Product(id="2", title="商品2", price=2000, platform="jd", url="https://example.com/item/2"),
        ]
        filtered = filter_products(products, price_min=3000)
        assert len(filtered) == 0
    
    def test_filter_empty_input(self):
        """测试空输入"""
        filtered = filter_products([])
        assert len(filtered) == 0
    
    def test_filter_invalid_price_range(self):
        """测试price_min > price_max"""
        products = [
            Product(id="1", title="商品1", price=1000, platform="jd", url="https://example.com/item/1"),
        ]
        with pytest.raises(ValueError, match="price_min不能大于price_max"):
            filter_products(products, price_min=2000, price_max=1000)
    
    def test_filter_invalid_rating(self):
        """测试min_rating超出范围"""
        products = [
            Product(id="1", title="商品1", price=1000, platform="jd", url="https://example.com/item/1"),
        ]
        with pytest.raises(ValueError, match="min_rating必须在0-5之间"):
            filter_products(products, min_rating=6.0)
    
    def test_filter_keywords(self):
        """测试关键词过滤"""
        products = [
            Product(id="1", title="iPhone 15 Pro", price=1000, platform="jd", url="https://example.com/item/1"),
            Product(id="2", title="小米14 Pro", price=1000, platform="jd", url="https://example.com/item/2"),
            Product(id="3", title="华为Mate 60", price=1000, platform="jd", url="https://example.com/item/3"),
        ]
        filtered = filter_products(products, keywords=["iPhone", "小米"])
        assert len(filtered) == 2
        assert all("iPhone" in p.title or "小米" in p.title for p in filtered)