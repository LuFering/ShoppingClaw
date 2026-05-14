from src.tools.compare import compare_products, ComparisonResult, _generate_report
from src.models.product import Product


class TestCompareTool:
    """对比工具测试类"""
    
    def test_compare_single_product(self):
        """测试单个商品对比"""
        products = [
            Product(id="1", title="iPhone 15", price=8000, platform="jd", url="https://example.com/item/1", rating=4.8, sales_count=10000),
        ]
        result = compare_products(products)
        assert isinstance(result, ComparisonResult)
        assert "单个商品对比" in result.report
        assert len(result.ranked_products) == 1
    
    def test_compare_multiple_products(self):
        """测试多个商品对比"""
        products = [
            Product(id="1", title="iPhone 15", price=8000, platform="jd", url="https://example.com/item/1", rating=4.8, sales_count=10000),
            Product(id="2", title="小米14", price=4000, platform="taobao", url="https://example.com/item/2", rating=4.5, sales_count=8000),
            Product(id="3", title="华为Mate 60", price=6000, platform="pdd", url="https://example.com/item/3", rating=4.7, sales_count=9000),
        ]
        result = compare_products(products)
        assert isinstance(result, ComparisonResult)
        assert len(result.ranked_products) == 3
        assert "商品对比报告" in result.report
    
    def test_compare_empty_list(self):
        """测试空列表"""
        result = compare_products([])
        assert isinstance(result, ComparisonResult)
        assert "没有商品可对比" in result.report
        assert len(result.ranked_products) == 0
    
    def test_compare_report_format(self):
        """测试报告格式"""
        products = [
            Product(id="1", title="iPhone 15", price=8000, platform="jd", url="https://example.com/item/1", rating=4.8, sales_count=10000),
            Product(id="2", title="小米14", price=4000, platform="taobao", url="https://example.com/item/2", rating=4.5, sales_count=8000),
        ]
        result = compare_products(products)
        assert "iPhone 15" in result.report
        assert "小米14" in result.report
        assert "价格" in result.report
        assert "评分" in result.report
        assert "销量" in result.report
    
    def test_compare_ranking_order(self):
        """测试排序是否正确"""
        products = [
            Product(id="1", title="商品1", price=10000, platform="jd", url="https://example.com/item/1", rating=3.0, sales_count=1000),
            Product(id="2", title="商品2", price=5000, platform="taobao", url="https://example.com/item/2", rating=4.5, sales_count=5000),
            Product(id="3", title="商品3", price=3000, platform="pdd", url="https://example.com/item/3", rating=4.8, sales_count=10000),
        ]
        result = compare_products(products)
        # 商品3应该排第一（价格低、评分高、销量高）
        assert result.ranked_products[0].id == "3"
        # 商品2应该排第二
        assert result.ranked_products[1].id == "2"
        # 商品1应该排最后
        assert result.ranked_products[2].id == "1"
    
    def test_compare_all_same_score(self):
        """测试所有商品评分相同"""
        products = [
            Product(id="1", title="商品1", price=5000, platform="jd", url="https://example.com/item/1", rating=4.5, sales_count=5000),
            Product(id="2", title="商品2", price=5000, platform="taobao", url="https://example.com/item/2", rating=4.5, sales_count=5000),
            Product(id="3", title="商品3", price=5000, platform="pdd", url="https://example.com/item/3", rating=4.5, sales_count=5000),
        ]
        # Python 的 sort 是稳定排序，得分相同时保持原顺序
        # 这个测试依赖 CPython 的稳定排序保证

        result = compare_products(products)
        # 所有商品得分相同，应该保持原顺序
        assert len(result.ranked_products) == 3
        assert result.ranked_products[0].id == "1"
        assert result.ranked_products[1].id == "2"
        assert result.ranked_products[2].id == "3"

    def test_generate_report_handles_invalid_price_display(self):
        """测试报告生成对异常价格值的展示兜底"""
        products = [
            Product.model_construct(
                id="1",
                title="异常价格商品",
                price="bad-price",
                state=1,
                platform="jd",
                url="https://example.com/item/1",
                rating=4.5,
                sales_count=5000,
            )
        ]

        report = _generate_report(products)

        assert "异常价格商品" in report
        assert "价格: ¥未知" in report

    def test_compare_handles_invalid_numeric_fields(self):
        """测试排序计算对异常数值字段的兜底处理"""
        products = [
            Product.model_construct(
                id="1",
                title="异常商品1",
                price="bad-price",
                state=1,
                platform="jd",
                url="https://example.com/item/1",
                rating="bad-rating",
                sales_count="bad-sales",
            ),
            Product.model_construct(
                id="2",
                title="正常商品",
                price=4999.0,
                state=1,
                platform="taobao",
                url="https://example.com/item/2",
                rating=4.6,
                sales_count=8000,
            ),
        ]

        result = compare_products(products)

        assert isinstance(result, ComparisonResult)
        assert len(result.ranked_products) == 2
        assert "商品对比报告" in result.report
