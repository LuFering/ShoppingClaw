import logging
import shutil
import subprocess
import os
import json
import re
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

# ==========================================
# MCP Server Registry (MCP服务器注册表)
# ==========================================
# 存放所有已配置的 MCP 服务器信息。
#
# type 类型:
#   - http:      远程 HTTP JSON-RPC
#   - stdio:     本地 stdio 子进程（如 sinataoke_cn）
#   - streamableHttp: SSE 流式 HTTP（如京东联盟 MCP，暂不可用）
#
# 注意: JD 不再通过 MCP 层 — 京东 SDK 已直接在 @tool 装饰器的 research/tools.py 中集成
MCP_SERVERS: Dict[str, Dict[str, Any]] = {
    # 淘宝/拼多多导购 MCP — 本地 stdio 子进程
    "taobao_mcp": {
        "type": "stdio",
        "description": "淘宝联盟 + 多多进宝商品搜索与转链（sinataoke_cn MCP）",
        "command": "sinataoke_cn.cmd",
        "env": {
            "ENV_URL": "https://config.sinataoke.cn/api/mcp/secret",
            "ENV_SECRET": "url:mcp.sinataoke.cn",
            "ENV_OVERRIDE": "false",
            # 以下凭据从系统环境变量注入（.env 已配置）
            "TAOBAO_SESSION": os.getenv("TAOBAO_SESSION", ""),
            "TAOBAO_PID": os.getenv("TAOBAO_PID", ""),
        },
    },
}

def get_mcp_serve_names() -> List[str]:
    """
    获取所有已注册的 MCP 服务器名称。
    
    返回:
        服务器名称列表，例如 ["mock_inventory_mcp"]
    """
    return list(MCP_SERVERS.keys())

# ── stdio 进程管理 ──
# 全局缓存：每个 stdio MCP 服务器对应一个持久子进程
_stdio_processes: Dict[str, subprocess.Popen] = {}

def _ensure_stdio_process(server_name: str, server_config: Dict[str, Any]) -> subprocess.Popen | None:
    """确保 stdio MCP 子进程已启动并完成初始化，返回可用进程。"""
    if server_name in _stdio_processes:
        proc = _stdio_processes[server_name]
        if proc.poll() is None:
            return proc  # 还在运行
        else:
            logger.warning(f"[MCP] stdio 进程 {server_name} 已退出，重新启动")
            del _stdio_processes[server_name]

    command = server_config.get("command", "")
    if not command:
        logger.error(f"[MCP] stdio 服务器 {server_name} 缺少 command 配置")
        return None

    # 跨平台命令解析：
    #   - Windows: 全局 npm 包的 .cmd shim 位于 %APPDATA%\npm\
    #   - Linux/macOS: npm -g 的 bin 在 PATH 中（无 .cmd 后缀），用 shutil.which 解析
    cmd_path: str | None = None
    if os.name == "nt":
        cmd_path = os.path.join(os.environ.get("APPDATA", ""), "npm", command)
        if not os.path.exists(cmd_path):
            logger.error(f"[MCP] 找不到命令: {cmd_path}")
            return None
    else:
        bare = command[:-4] if command.endswith(".cmd") else command
        cmd_path = shutil.which(bare)
        if not cmd_path:
            logger.error(
                f"[MCP] 找不到命令: {bare}（请确认已在服务器安装 Node.js 并 "
                f"npm install -g {bare}）"
            )
            return None

    env = {**os.environ, **server_config.get("env", {})}
    try:
        proc = subprocess.Popen(
            [cmd_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            env=env,
        )
    except Exception as exc:
        logger.error(f"[MCP] 启动 stdio 进程 {server_name} 失败: {exc}")
        return None

    import time
    time.sleep(8)  # 等进程完全启动
    if proc.poll() is not None:
        _, err = proc.communicate(timeout=5)
        logger.error(f"[MCP] stdio 进程 {server_name} 启动后立即退出: {err[:300]}")
        return None

    # 执行 MCP initialize 握手
    try:
        proc.stdin.write(json.dumps({"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"ShoppingClaw","version":"1.0"}},"id":1}) + "\n")
        proc.stdin.flush()
        time.sleep(3)
        line = proc.stdout.readline()
        if not line.strip():
            logger.error(f"[MCP] stdio 进程 {server_name} initialize 无响应")
            proc.terminate()
            return None
        r = json.loads(line)
        svr = r.get("result", {}).get("serverInfo", {})
        logger.info(f"[MCP] {server_name} 初始化成功: {svr.get('name')} v{svr.get('version')}")

        proc.stdin.write(json.dumps({"jsonrpc":"2.0","method":"notifications/initialized","params":{}}) + "\n")
        proc.stdin.flush()
        _stdio_processes[server_name] = proc
        return proc
    except Exception as exc:
        logger.error(f"[MCP] stdio 进程 {server_name} 初始化失败: {exc}")
        proc.terminate()
        return None


def _get_stdio_tool_specs(server_name: str, server_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 stdio MCP 服务器拉取工具列表。"""
    proc = _ensure_stdio_process(server_name, server_config)
    if proc is None or proc.stdin is None or proc.stdout is None:
        return []
    try:
        import time
        proc.stdin.write(json.dumps({"jsonrpc":"2.0","method":"tools/list","params":{},"id":2}) + "\n")
        proc.stdin.flush()
        time.sleep(5)
        line = proc.stdout.readline()
        r = json.loads(line)
        tools = r.get("result", {}).get("tools", [])
        specs = []
        seen_names: set[str] = set()
        for t in tools:
            raw_name = t.get("name", "")
            # LLM 接口要求工具名 ^[a-zA-Z0-9_-]+$（MCP 原名常含 '.'，如 taobao.searchMaterial）：
            # 对外用净化名，原始名存 _mcp_tool_name 供实际调用回查
            safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_name) or "mcp_tool"
            while safe_name in seen_names:
                safe_name += "_"
            seen_names.add(safe_name)
            schema = t.get("inputSchema", {}) or {}
            # —— 对已知必填缺失的淘宝搜索工具做修补：接口要求 q 与 cat 至少一个，
            # 但 MCP schema 声明 required=[]（导致 LLM 以为可都不传 → 400）。
            # 这里强制把 required 标成 ["q"]，并保留 cat 可选项，让 LLM 至少传搜索词。
            # （q/cat 兜底在 mcp_tool_adapter 的 stdio executor 里再做一层）
            if raw_name == "taobao.searchMaterial":
                props = schema.get("properties", {}) or {}
                if "q" in props and (schema.get("required") is None or len(schema.get("required", [])) == 0):
                    schema = {**schema, "required": ["q"]}
            specs.append({
                "name": safe_name,
                "description": t.get("description", ""),
                "inputSchema": schema,
                "_mcp_tool_name": raw_name,
                "_mcp_server_name": server_name,
                "_mcp_server_type": "stdio",
            })
        return specs
    except Exception as exc:
        logger.error(f"[MCP] 从 {server_name} 拉取工具列表失败: {exc}")
        return []


def _call_stdio_tool(server_name: str, server_config: Dict[str, Any], tool_name: str, arguments: Dict[str, Any]) -> Any:
    """调用 stdio MCP 工具（同步版本，必须在线程中调用以避免阻塞事件循环）。"""
    proc = _ensure_stdio_process(server_name, server_config)
    if proc is None or proc.stdin is None or proc.stdout is None:
        return {"error": "stdio MCP 进程不可用"}
    try:
        import time
        proc.stdin.write(json.dumps({"jsonrpc":"2.0","method":"tools/call","params":{"name":tool_name,"arguments":arguments},"id":100}) + "\n")
        proc.stdin.flush()
        time.sleep(5)
        line = proc.stdout.readline()
        r = json.loads(line)
        content = r.get("result", {}).get("content", [{}])
        if content and isinstance(content, list) and len(content) > 0:
            return content[0].get("text", json.dumps(r))
        return json.dumps(r)
    except Exception as exc:
        logger.error(f"[MCP] stdio 工具调用 {tool_name} 失败: {exc}")
        return {"error": str(exc)}


async def call_stdio_tool_async(
    server_name: str,
    server_config: Dict[str, Any],
    tool_name: str,
    arguments: Dict[str, Any],
) -> Any:
    """调用 stdio MCP 工具（异步版本，使用线程池避免阻塞事件循环）。"""
    import asyncio
    return await asyncio.to_thread(
        _call_stdio_tool, server_name, server_config, tool_name, arguments
    )

async def get_tools_from_all_servers() -> List[Dict[str, Any]]:
    """
    从所有注册的 MCP 服务器拉取并聚合工具。
    
    注意：
    这里返回的不是可执行的 Callable 函数，而是工具的描述字典 (Tool Spec)。
    `mcp_tool_adapter` 会负责把这些字典转换为 LangChain 可用的 Tool 对象。
    
    返回:
        聚合后的所有工具描述列表
    """
    all_tools_specs: List[Dict[str, Any]] = []
    
    for server_name, server_config in MCP_SERVERS.items():
        try:
            logger.info(f"正在从 MCP 服务器拉取工具: {server_name}")
            srv_type = server_config.get("type", "http")
            
            if srv_type == "stdio":
                tools_specs = _get_stdio_tool_specs(server_name, server_config)
            else:
                logger.warning(f"MCP 服务器 {server_name} 的 type={srv_type} 暂未实现")
                tools_specs = []
                
            all_tools_specs.extend(tools_specs)
            logger.info(f"成功从 {server_name} 加载了 {len(tools_specs)} 个工具。")
        except Exception as e:
            # 工程性防御：一个 MCP Server 挂了，不能影响其他 Server 的工具加载
            logger.error(f"从 MCP 服务器 {server_name} 拉取工具失败: {e}", exc_info=True)
            continue
            
    return all_tools_specs