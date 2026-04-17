import pytest
from src.agents.common.toolkits.shopping.compare_tool import product_compare
from src.models.product import Product

@pytest.fixture
def mock_products():
    return [
        Product(id="1", title="Apple iPhone 15", price=5999.0, platform="jd", rating=4.8, sales_count=1000, url="http://test.com/1"),
        Product(id="2", title="Apple iPhone 15", price=5799.0, platform="taobao", rating=4.7, sales_count=800, url="http://test.com/2"),
        Product(id="3", title="Apple iPhone 15", price=5899.0, platform="pdd", rating=4.9, sales_count=1500, url="http://test.com/3"),
    ]

def test_product_compare_success(mock_products):
    """测试多商品正常对比"""
    result = product_compare.invoke({"products": mock_products})
    
    assert result["error"] is None
    assert isinstance(result["report"], str)
    assert len(result["report"]) > 0
    assert "商品对比报告" in result["report"]
    
    assert len(result["ranked_products"]) == 3
    # 验证排序是否正确（根据原算法，PDD价格居中但评分和销量最高，可能会排前面，但这里只要验证类型和数量对就行，算法由业务侧决定）
    assert isinstance(result["ranked_products"][0], Product)

def test_product_compare_empty_list():
    """测试工程性防御 1：空列表"""
    result = product_compare.invoke({"products": []})
    
    assert result["error"] is not None
    assert "无法生成对比报告" in result["report"]
    assert result["ranked_products"] == []

def test_product_compare_single_product(mock_products):
    """测试工程性防御 2：单个商品"""
    single_product = [mock_products[0]]
    result = product_compare.invoke({"products": single_product})
    
    assert result["error"] is None
    assert "只有一个商品" in result["report"]
    assert len(result["ranked_products"]) == 1
    assert result["ranked_products"][0].title == "Apple iPhone 15"

def test_product_compare_missing_fields():
    """测试容错：商品缺失某些可选字段（如没有销量、没有评分）"""
    bad_products = [
        Product(id="1", title="A", price=100.0, platform="jd", url="http://test.com/1"),  # 没评分没销量
        Product(id="2", title="B", price=200.0, platform="taobao", rating=4.0, url="http://test.com/2"), # 没销量
    ]
    result = product_compare.invoke({"products": bad_products})
    
    assert result["error"] is None
    assert len(result["ranked_products"]) == 2
    # 即使缺字段，底层算法和包装层也能算出结果，不会崩溃
