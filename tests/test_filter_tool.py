import pytest
from src.agents.common.toolkits.shopping.filter_tool import product_filter
from src.models.product import Product

# 构建测试用假数据 (复用 product 模型结构)
@pytest.fixture
def mock_products():
    return [
        Product(id="1", title="Apple iPhone 15", price=5999.0, platform="jd", rating=4.8, url="http://test.com/1"),
        Product(id="2", title="Xiaomi 14", price=3999.0, platform="taobao", rating=4.6, url="http://test.com/2"),
        Product(id="3", title="Huawei Mate 60", price=6999.0, platform="pdd", rating=4.9, url="http://test.com/3"),
        Product(id="4", title="Cheap Phone", price=999.0, platform="pdd", rating=3.5, url="http://test.com/4"),
    ]

def test_product_filter_price_range(mock_products):
    """测试价格区间过滤"""
    # invoke 是 LangChain Tool 的调用方式，传入的字典会自动被 Pydantic 模型校验
    result = product_filter.invoke({
        "products": mock_products,
        "price_min": 2000.0,
        "price_max": 6000.0
    })
    
    assert result["error"] is None
    assert len(result["products"]) == 2
    # 断言只留下了 iPhone 和 Xiaomi，排除了 Huawei (太贵) 和 Cheap Phone (太便宜)
    assert all(2000.0 <= p.price <= 6000.0 for p in result["products"])

def test_product_filter_platform_and_rating(mock_products):
    """测试多条件组合过滤 (平台 + 评分)"""
    result = product_filter.invoke({
        "products": mock_products,
        "platforms": ["pdd"],
        "min_rating": 4.0
    })
    
    assert result["error"] is None
    # 拼多多有 2 款手机，但 Cheap Phone 评分低于 4.0，所以只剩 1 款 Huawei
    assert len(result["products"]) == 1
    assert result["products"][0].title == "Huawei Mate 60"

def test_product_filter_empty_list():
    """测试工程性防御 1：传入空列表"""
    result = product_filter.invoke({
        "products": [],
        "price_min": 100.0
    })
    
    assert result["error"] is None
    assert result["products"] == []

def test_product_filter_invalid_price_range(mock_products):
    """测试工程性防御 2：拦截底层异常 (min > max)"""
    result = product_filter.invoke({
        "products": mock_products,
        "price_min": 5000.0,
        "price_max": 1000.0
    })
    
    assert result["error"] is not None
    assert "过滤条件有误" in result["error"]
    # 核心设计：发生错误时，为了防止大模型丢掉已有的商品，我们原样退回输入的商品列表
    assert len(result["products"]) == 4 
