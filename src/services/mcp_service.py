from typing import Any, Callable

MCP_SERVERS:dict[str,dict[str,Any]]={}

#TODO:MCP在项目生态拓展阶段再继续开发，目前先暂时不开发
def get_mcp_serve_names()->list[str]:
    return list(MCP_SERVERS.keys())
async def get_tools_from_all_servers()->list[Callable[...,Any]]:
    all_tools=[]
    for server_name in MCP_SERVERS.keys():
        tools =await get_mcp_tools()