import pytest
from src.services.mcp_service import get_mcp_serve_names, get_tools_from_all_servers, MCP_SERVERS

def test_get_mcp_serve_names():
    """测试获取已注册的 MCP 服务器列表"""
    names = get_mcp_serve_names()
    assert isinstance(names, list)
    assert "mock_inventory_mcp" in names

@pytest.mark.asyncio
async def test_get_tools_from_all_servers():
    """测试从所有 MCP 服务器聚合工具 (当前为 Mock 数据)"""
    tools = await get_tools_from_all_servers()
    
    assert isinstance(tools, list)
    assert len(tools) > 0
    
    # 验证提取出的 Tool Spec 是否符合预期结构
    first_tool = tools[0]
    assert "name" in first_tool
    assert "description" in first_tool
    assert "inputSchema" in first_tool
    assert "_mcp_server_name" in first_tool
    
    assert first_tool["name"] == "get_product_inventory"
    assert first_tool["_mcp_server_name"] == "mock_inventory_mcp"

@pytest.mark.asyncio
async def test_mcp_server_failure_isolation(monkeypatch):
    """测试工程性防御：某个 MCP 服务器挂了不影响其他服务器"""
    
    # 动态注入一个必定报错的 fake 服务器
    fake_servers = {
        "mock_inventory_mcp": MCP_SERVERS["mock_inventory_mcp"],
        "bad_server": {"url": "http://bad.com"}
    }
    
    monkeypatch.setattr("src.services.mcp_service.MCP_SERVERS", fake_servers)
    
    # mock fetch 函数，如果是 bad_server 抛异常，否则正常返回
    original_fetch = src.services.mcp_service._fetch_tools_from_server
    
    async def mock_fetch(server_name, config):
        if server_name == "bad_server":
            raise ConnectionError("服务器连接失败")
        return await original_fetch(server_name, config)
        
    import src.services.mcp_service
    monkeypatch.setattr(src.services.mcp_service, "_fetch_tools_from_server", mock_fetch)
    
    # 即使 bad_server 抛出异常，整个函数也不应崩溃，并返回好的 server 的工具
    tools = await get_tools_from_all_servers()
    
    assert len(tools) == 1
    assert tools[0]["_mcp_server_name"] == "mock_inventory_mcp"
