import pytest
from src.agents.common.toolkits.shopping.search_tool import product_search

def test_product_search_success():
    """测试正常的商品搜索"""
    # product_search 是一个带有 @tool 装饰器的函数
    # 我们可以通过 invoke() 方法来调用它，就像 Agent 那样
    result = product_search.invoke({"query": "iPhone 15", "platforms": ["jd"], "limit": 2})
    
    assert isinstance(result, dict)
    assert result["error"] is None
    assert "products" in result
    assert len(result["products"]) > 0
    # 验证返回的确实是 JD 平台的数据
    assert all(p.platform == "jd" for p in result["products"])

def test_product_search_empty_query():
    """测试传入空查询时的容错能力"""
    # 故意传入空字符串
    result = product_search.invoke({"query": "   ", "platforms": ["jd"], "limit": 2})
    
    assert isinstance(result, dict)
    assert result["error"] is not None
    assert "query must not be empty" in result["error"].lower()
    assert result["products"] == []

def test_product_search_limit_exceeded():
    """测试 limit 越界时的容错能力"""
    result = product_search.invoke({"query": "iPhone 15", "platforms": ["jd"], "limit": 200})
    
    assert isinstance(result, dict)
    assert result["error"] is not None
    assert "limit must be between" in result["error"].lower()
    assert result["products"] == []

def test_product_search_no_platforms():
    """测试不传 platforms，默认搜索全平台"""
    result = product_search.invoke({"query": "iPhone 15", "limit": 1})
    
    assert isinstance(result, dict)
    assert result["error"] is None
    # 我们的 MockCrawler 里有 3 个平台的数据，limit=1 意味着每个平台返回 1 个，总共 3 个
    assert len(result["products"]) == 3
