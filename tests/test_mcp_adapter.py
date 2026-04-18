import pytest
from langchain.tools import BaseTool

from src.services.mcp_tool_adapter import adapt_mcp_tools, convert_mcp_spec_to_langchain_tool

# 提供测试用的 Mock Tool Spec
@pytest.fixture
def mock_inventory_spec():
    return {
        "name": "get_product_inventory",
        "description": "获取指定商品的实时库存情况",
        "inputSchema": {
            "type": "object",
            "properties": {
                "product_id": {"type": "string", "description": "商品ID，例如 'jd_mock_001'"},
                "region": {"type": "string", "description": "发货区域，如 '北京'"}
            },
            "required": ["product_id"]
        },
        "_mcp_server_name": "mock_inventory_mcp",
        "_mcp_server_url": "http://localhost:8080/mcp"
    }

def test_convert_mcp_spec_to_langchain_tool(mock_inventory_spec):
    """测试单个 Tool Spec 转换为 LangChain Tool"""
    tool = convert_mcp_spec_to_langchain_tool(mock_inventory_spec)
    
    # 验证是否返回了 LangChain 框架认识的工具对象
    assert isinstance(tool, BaseTool)
    
    # 验证元数据是否正确映射
    assert tool.name == "get_product_inventory"
    assert "获取指定商品的实时库存情况" in tool.description
    
    # 验证执行器是否能被调用并返回预期的 Mock 结果
    # 这里因为配置的 url 是 localhost:8080，适配器内部会拦截 HTTP 请求直接返回 Mock 数据
    result = tool.invoke({"product_id": "iphone_15", "region": "上海"})
    
    assert isinstance(result, dict)
    assert result.get("status") == "success"
    assert result.get("stock") == 99
    assert "iphone_15" in result.get("message")

def test_adapt_mcp_tools_list(mock_inventory_spec):
    """测试批量转换功能"""
    specs = [mock_inventory_spec]
    
    # 也就是 Day 5 返回的结果传给 Day 6 的适配器
    langchain_tools = adapt_mcp_tools(specs)
    
    assert isinstance(langchain_tools, list)
    assert len(langchain_tools) == 1
    assert isinstance(langchain_tools[0], BaseTool)
    assert langchain_tools[0].name == "get_product_inventory"
