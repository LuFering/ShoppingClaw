"""MCP 服务器包 — MCP 协议工具集成。

当前架构:
- stdio MCP: sinataoke_cn（淘宝/拼多多），通过子进程 stdin/stdout JSON-RPC 通信
- JD 平台: 不再走 MCP 层，SDK 直接在 @tool 装饰器的 research/tools.py 中集成

历史遗留:
- jd_product_mcp.py: JD MCP 本地封装（已弃用，仅作参考）
"""
