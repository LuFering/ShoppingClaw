import logging
import re
from typing import Any, Callable, Dict, List, Optional
import requests

from langchain.tools import BaseTool
from langchain.tools import tool as langchain_tool
from langchain_core.tools import StructuredTool
from pydantic import Field, create_model

logger = logging.getLogger(__name__)

def _create_mcp_executor(tool_spec: Dict[str, Any]) -> Callable[..., Any]:
    """
    创建一个闭包函数，用于实际执行 MCP 远程调用或本地 stdio 调用。

    - stdio 模式（type=stdio）：通过 stdin/stdout JSON-RPC 与本地子进程通信（如 sinataoke_cn）
    - http 模式（type=http/streamableHttp）：通过 HTTP POST 发送 JSON-RPC 请求
    """
    server_type = tool_spec.get("_mcp_server_type", "http")
    server_name = tool_spec.get("_mcp_server_name", "")
    # 实际调用用 MCP 原始名（如 taobao.searchMaterial）；spec.name 是 LLM 用的净化名
    tool_name = tool_spec.get("_mcp_tool_name") or tool_spec.get("name")

    # ── stdio 模式：通过子进程 stdin/stdout 通信 ──
    if server_type == "stdio":
        def executor(**kwargs: Any) -> Any:
            # —— 参数解平：LangChain 以 invoke({'kwargs': {...}}) 调用，真实参数嵌套在 kwargs 子键里 ——
            args = dict(kwargs)
            if isinstance(args.get("kwargs"), dict):
                args = {**args["kwargs"], **args}  # 内层优先，外层同名覆盖
                args.pop("kwargs", None)
            # —— 兜底：LLM 可能不给 MCP 要求的必填键 q/cat，用近义键补 ——
            if not args.get("q") and not args.get("cat"):
                args["q"] = args.get("keyword") or args.get("query") or args.get("kw") or ""
            logger.info(f"[MCP Adapter] stdio 工具调用: {tool_name}, 参数: {args}")
            try:
                from src.services.mcp_service import _call_stdio_tool, MCP_SERVERS
                server_config = MCP_SERVERS.get(server_name, {})
                res = _call_stdio_tool(server_name, server_config, tool_name or "unknown", args)
                return res
            except Exception as exc:
                logger.error(f"[MCP Adapter] stdio 工具 {tool_name} 执行失败: {exc}")
                return {"error": str(exc)}
        return executor

    # ── http 模式（原有逻辑） ──
    server_url = tool_spec.get("_mcp_server_url")
    def executor(**kwargs: Any) -> Any:
        logger.info(f"[MCP Adapter] 准备执行远程工具: {tool_name}, 参数: {kwargs}")
        
        if not server_url:
            logger.warning(f"[MCP Adapter] 未配置 URL，返回空结果。")
            return {"status": "error", "message": "MCP server URL not configured"}
        
        try:
            payload = {
                "jsonrpc": "2.0",
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": kwargs
                },
                "id": 1
            }
            
            response = requests.post(server_url, json=payload, timeout=10)
            response.raise_for_status()
            
            return response.json()
            
        except requests.RequestException as e:
            error_msg = f"调用远程 MCP 工具 {tool_name} 失败: {str(e)}"
            logger.error(error_msg)
            return {"error": error_msg}
            
    return executor


# MCP inputSchema 的 JSON 类型 → Python 类型。未知类型回退 Any，
# 避免因 MCP 侧新增 schema 写法导致整件工具构建失败。
_MCP_TYPE_MAP: Dict[str, Any] = {
    "string": str,
    "integer": int,
    "number": float,
    "boolean": bool,
    "array": list,
    "object": dict,
}


def _build_args_model(tool_name: str, input_schema: Dict[str, Any]):
    """把 MCP inputSchema 的 properties 转成 pydantic 模型，作为 args_schema。"""
    props = (input_schema or {}).get("properties") or {}
    required = set((input_schema or {}).get("required") or [])
    fields: Dict[str, Any] = {}
    for key, spec in props.items():
        if not isinstance(spec, dict):
            continue
        py_type = _MCP_TYPE_MAP.get(spec.get("type"), Any)
        desc = (spec.get("description") or "")[:200]
        if key in required:
            fields[key] = (py_type, Field(..., description=desc))
        else:
            fields[key] = (Optional[py_type], Field(None, description=desc))
    if not fields:
        return None
    safe = re.sub(r"[^A-Za-z0-9_]", "_", tool_name)
    return create_model(safe, **fields)



# ═══ MCP 工具的接入白名单（2026-09-21）═══
# 26 个 MCP 工具里绝大多数是变现 / 转链 / 订单类（createTpwd、promotionZone、
# getOrderDetails …），对购前决策没有价值，且会污染工具列表、诱导模型跑偏。
# 只放行「搜索 + 详情 + 转链」三类：
#   search  —— 拿候选商品与价格
#   detail  —— 补规格
#   convert —— 把商品转成可直接打开的链接（item_url 只在部分返回里出现，
#              转链是拿稳定 url 的正规途径）
# 其余一律不注册，因此也不会出现在任何智能体的工具清单里。
_MCP_TOOL_WHITELIST: set[str] = {
    # 淘宝
    "taobao_searchMaterial",
    "taobao_getItemInfo",
    "taobao_convertLink",
    # 拼多多
    "pdd_goods_search",
    "pdd_goods_detail",
    "pdd_goods_recommend",
    "pdd_goods_prom_url",
}

# MCP 工具的前端展示元数据（图标 / 中文名），与自建工具保持同一种口径。
_MCP_TOOL_DISPLAY: Dict[str, tuple[str, str]] = {
    "taobao_searchMaterial": ("\U0001f50e", "淘宝商品搜索"),
    "taobao_getItemInfo": ("\U0001f4cb", "淘宝商品详情"),
    "taobao_convertLink": ("\U0001f517", "淘宝转链"),
    "pdd_goods_search": ("\U0001f50e", "拼多多商品搜索"),
    "pdd_goods_detail": ("\U0001f4cb", "拼多多商品详情"),
    "pdd_goods_recommend": ("\U0001f50e", "拼多多商品推荐"),
    "pdd_goods_prom_url": ("\U0001f517", "拼多多转链"),
}


def _register_mcp_tool(tool_obj: Any, tool_spec: Dict[str, Any]) -> None:
    """把单个 MCP 工具注册进注册表（仅白名单内）。

    注册失败不能影响工具本身可用：MCP 已经能查数据了，退化成「未注册」
    只是少一层 Runtime 包装，不应该让整批工具加载失败。
    """
    name = getattr(tool_obj, "name", "") or ""
    if name not in _MCP_TOOL_WHITELIST:
        logger.info(f"[MCP Adapter] {name} 不在接入白名单内，仅构造不注册")
        return
    icon, display = _MCP_TOOL_DISPLAY.get(name, ("\U0001f9f0", name))
    try:
        from src.agents.common.toolkits.registry import register_external_tool

        register_external_tool(
            tool_obj,
            category="mcp",
            tags=["MCP", "商品"],
            display_name=display,
            icon=icon,
            # MCP 走 stdio 子进程 + 远程 API，链路比自建工具长；
            # 给 60s 上限，避免长尾把 SSE 流挂死。
            timeout=60,
            max_retries=0,
        )
        logger.info(f"[MCP Adapter] 已注册 MCP 工具: {name} ({display})")
    except Exception as exc:
        logger.error(f"[MCP Adapter] 注册 {name} 失败（工具仍可用，仅缺 Runtime 包装）: {exc}")



def convert_mcp_spec_to_langchain_tool(tool_spec: Dict[str, Any]) -> BaseTool:
    """
    将单个 MCP Tool Spec (JSON 描述) 转换为 LangChain 的 BaseTool。
    
    使用 @tool 装饰器动态创建工具，与项目其他工具保持一致。
    """
    # 提取基本信息
    name = tool_spec.get("name", "unknown_mcp_tool")
    description = tool_spec.get("description", "A remote MCP tool")
    
    # 创建执行器
    executor_func = _create_mcp_executor(tool_spec)
    
    # 使用 @tool 装饰器动态创建工具
    # ═══ 2026-09-21 修复：用 inputSchema 建 args_schema，不再用 @tool 包装 **kwargs ═══
    # 旧实现 `langchain_tool(description=...)(executor_func)` 对 `(**kwargs)` 签名
    # 生成的 args_schema 只有一个 `kwargs` 字段，LLM 传来的真实参数在 schema 校验
    # 阶段即被丢弃，executor 恒收到空 dict（实测 taobao.searchMaterial 因此永远报
    # sub_code 30002「q与cat不能都为空」）。改为显式构造 pydantic 模型。
    args_model = _build_args_model(name, tool_spec.get("inputSchema") or {})
    if args_model is None:
        # 无参数的工具：退化到原路径（此时空 schema 无害）
        executor_func.__name__ = name
        executor_func.__doc__ = description
        tool_obj = langchain_tool(description=description)(executor_func)
        tool_obj.name = name
        return tool_obj

    # MCP 侧（zod）不接受显式 null，而 pydantic 会把未提供的可选字段填成 None。
    # 这里剥掉 None / 空串，只下发调用方真实提供的参数。
    def _clean_executor(**kwargs: Any) -> Any:
        clean = {k: v for k, v in kwargs.items() if v is not None and v != ""}
        return executor_func(**clean)

    tool_obj = StructuredTool(
        name=name,
        description=description,
        func=_clean_executor,
        args_schema=args_model,
    )

    # 来源标记：主智能体据此把这些业务工具排除在自己的工具集外
    # （编排护栏要求主智能体不持有任何业务工具）。
    tool_obj._is_mcp_tool = True

    # ═══ 2026-09-21：注册进全局注册表并注入 Runtime 包装 ═══
    # MCP 工具是运行时构造的，不在 @tool 的导入期装饰路径上。不注册的话：
    #   · subagents.yaml 写不出这些工具名（_get_tool_by_name 读注册表）
    #   · LifecycleHandler 不发事件 → 前端看不到 MCP 调用轨迹
    #   · 没有 TimeoutRetryHandler 兜底 → MCP 子进程卡住会拖死整条流
    _register_mcp_tool(tool_obj, tool_spec)
    return tool_obj

async def adapt_mcp_tools(tool_specs: List[Dict[str, Any]]) -> List[Callable[..., Any]]:
    """
    将一组 MCP Tool Specs 转换为一组可被 LangGraph 调用的 LangChain 工具。
    
    注意：此函数现在是异步的，以保持与 MCP 服务层的一致性。
    虽然工具转换本身是 CPU 密集型操作，但异步接口避免了混合调用模式。
    """
    langchain_tools = []
    for spec in tool_specs:
        try:
            tool = convert_mcp_spec_to_langchain_tool(spec)
            langchain_tools.append(tool)
        except Exception as e:
            logger.error(f"转换 MCP 工具 {spec.get('name')} 失败: {e}")
            
    return langchain_tools

def adapt_mcp_tools_sync(tool_specs: List[Dict[str, Any]]) -> List[Callable[..., Any]]:
    """
    同步版本的 MCP 工具转换函数，用于向后兼容。
    
    注意：在异步上下文中，请优先使用 adapt_mcp_tools()。
    警告：此函数可能在线程安全方面存在问题，建议在新代码中使用异步版本。
    """
    import asyncio
    
    # 线程安全检查：如果已有事件循环运行，使用线程安全方式调用
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # 在已有事件循环的线程中，创建新的事件循环
            import asyncio
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                return new_loop.run_until_complete(adapt_mcp_tools(tool_specs))
            finally:
                new_loop.close()
    except RuntimeError:
        # 没有事件循环，安全使用 asyncio.run
        pass
    
    # 默认使用 asyncio.run（线程安全）
    return asyncio.run(adapt_mcp_tools(tool_specs))