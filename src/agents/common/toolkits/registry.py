"""工具注册表 - 基于 LangChain 的拓展装饰器。

六层框架之「注册层」：声明式绑定工具元数据（分类、标签、超时、重试、权限等），
并在注册时注入 Runtime 执行包装，确保所有工具调用经过统一的 Handler Chain。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable, Any

from langchain.tools import tool as langchain_tool

logger = logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# 元数据模型
# ════════════════════════════════════════════════════════════════

@dataclass
class ToolExtraMetadata:
    """工具附加元数据（分类、前端展示 + 运行时策略）。

    由 @tool 装饰器在注册时自动填充，存入全局注册表供 Runtime、发现层、
    中间件等消费。
    """

    # ── 展示元数据（原有） ──
    category: str = "buildin"             # 分类：buildin | research | analyst | critic
    tags: list[str] = field(default_factory=list)  # 标签：["搜索", "官方API"]
    display_name: str = ""                # 中文显示名称
    icon: str = ""                        # emoji 图标

    # ── 运行时策略（新增） ──
    timeout: int = 30                     # 单次执行超时（秒），0 = 不限
    max_retries: int = 0                  # 最大重试次数
    retry_on: tuple[type[Exception], ...] = ()  # 触发重试的异常类型
    rate_limit: dict | None = None        # {"max_per_min": 30}
    required_permissions: list[str] = field(default_factory=list)  # 调用所需权限

    # ── Schema（新增） ──
    return_schema: type | None = None     # 输出 Pydantic Schema（声明式）
    version: str = "1.0.0"               # 工具版本号


# ════════════════════════════════════════════════════════════════
# 全局注册表
# ════════════════════════════════════════════════════════════════

_extra_registry: dict[str, ToolExtraMetadata] = {}
_all_tool_instances: list = []


def get_extra_metadata(tool_name: str) -> ToolExtraMetadata | None:
    return _extra_registry.get(tool_name)


def get_all_extra_metadata() -> dict[str, ToolExtraMetadata]:
    return _extra_registry.copy()


def get_all_tool_instances() -> list:
    return _all_tool_instances.copy()


# ════════════════════════════════════════════════════════════════
# 核心装饰器
# ════════════════════════════════════════════════════════════════

def tool(
    # ── 展示元数据 ──
    category: str = "buildin",
    tags: list[str] | None = None,
    display_name: str = "",
    icon: str = "",
    # ── 运行时策略 ──
    timeout: int = 30,
    max_retries: int = 0,
    retry_on: tuple[type[Exception], ...] = (),
    rate_limit: dict | None = None,
    required_permissions: list[str] | None = None,
    # ── Schema ──
    return_schema: type | None = None,
    version: str = "1.0.0",
    # ── 原有参数 ──
    name: str | None = None,
    description: str | None = None,
    args_schema: type | None = None,
    return_direct: bool = False,
    # ── Handler Chain 定制 ──
    handlers: list | None = None,
):
    """基于 LangChain 的拓展装饰器，绑定元数据并注入 Runtime 执行包装。

    使用示例:
        @tool(
            category="research", tags=["搜索"], display_name="商品搜索",
            timeout=15, max_retries=2, retry_on=(ConnectionError,),
            rate_limit={"max_per_min": 30},
        )
        def search_products(keyword: str, page: int = 1) -> dict:
            ...

    Args:
        handlers: 覆盖默认 Handler Chain，用于 per-tool 定制（如内部工具跳过权限校验）
    """

    def decorator(func: Callable) -> Callable:
        original_func = func

        # 1. 应用 LangChain 原生装饰器 → 创建 StructuredTool
        tool_obj = langchain_tool(
            description=description or func.__doc__ or "",
            args_schema=args_schema,
            return_direct=return_direct,
        )(func)

        # 2. 如果指定了 name，手动覆盖工具名称
        if name:
            tool_obj.name = name

        tool_name = tool_obj.name

        # 3. 注册扩展元数据
        _extra_registry[tool_name] = ToolExtraMetadata(
            category=category,
            tags=tags or [],
            display_name=display_name or tool_name,
            icon=icon,
            timeout=timeout,
            max_retries=max_retries,
            retry_on=retry_on,
            rate_limit=rate_limit,
            required_permissions=required_permissions or [],
            return_schema=return_schema,
            version=version,
        )

        # 4. 注入 Runtime 执行包装
        #    所有工具调用经过 RuntimeChain → 统一管控超时/重试/权限/限流/结果封装
        _inject_runtime_wrapper(tool_obj, tool_name, original_func, handlers)

        # 5. 自动收集工具实例
        _all_tool_instances.append(tool_obj)

        return tool_obj

    return decorator


# ════════════════════════════════════════════════════════════════
# Runtime 注入
# ════════════════════════════════════════════════════════════════


def register_external_tool(
    tool_obj: Any,
    *,
    category: str = "mcp",
    tags: list[str] | None = None,
    display_name: str = "",
    icon: str = "",
    timeout: int = 30,
    max_retries: int = 0,
    retry_on: tuple[type[Exception], ...] = (),
    handlers: list | None = None,
) -> Any:
    """把运行时动态构造的工具（如 MCP）注册进注册表并注入 Runtime 包装。

    与 @tool 装饰器的区别：@tool 在**导入时**装饰函数定义；而 MCP 工具要等
    `tools/list` 返回后才能构造，只能在**运行时**注册。两者最终落到同一套
    注册表与 Runtime 链，因此：
      · `_get_tool_by_name()` 能找到它 → 可写进 subagents.yaml 的工具清单
      · `LifecycleHandler` 会发 tool_start / tool_complete → 前端能看到轨迹
      · `TimeoutRetryHandler` 按 timeout 兜底 → MCP 子进程卡住不会拖死整条流

    注意：本函数不负责构造工具，只负责「登记 + 包装」，构造仍由调用方
    （mcp_tool_adapter）完成，避免注册表反向依赖具体的工具来源。
    """
    tool_name = getattr(tool_obj, "name", "") or ""
    if not tool_name:
        raise ValueError("register_external_tool: 工具缺少 name")

    # 幂等：重复注册（同一进程内多次拉取 MCP 工具）时只保留一份，
    # 否则 _all_tool_instances 会累积重复项，工具列表随对话轮次膨胀。
    existing = next(
        (t for t in _all_tool_instances if getattr(t, "name", None) == tool_name),
        None,
    )
    if existing is not None:
        return existing

    _extra_registry[tool_name] = ToolExtraMetadata(
        category=category,
        tags=tags or [],
        display_name=display_name or tool_name,
        icon=icon,
        timeout=timeout,
        max_retries=max_retries,
        retry_on=retry_on,
        required_permissions=[],
        version="1.0.0",
    )

    # 注入 Runtime 包装：包的是工具当前的同步入口（MCP executor 是同步函数，
    # 走 _call_stdio_tool 阻塞 IO，由 ExecuteHandler 放进线程池执行）。
    original = getattr(tool_obj, "func", None)
    if callable(original):
        _inject_runtime_wrapper(tool_obj, tool_name, original, handlers)

    _all_tool_instances.append(tool_obj)
    return tool_obj



def _inject_runtime_wrapper(
    tool_obj: Any,
    tool_name: str,
    original_func: Callable,
    custom_handlers: list | None,
) -> None:
    """将 Runtime 执行包装注入到工具对象中。

    所有工具调用（tool.ainvoke / tool.invoke）都会先经过 Runtime，
    再执行原始函数。这使得超时、重试、权限、限流等横切关注点由
    Handler Chain 统一管控。
    """
    # ═══ 2026-09-23：标记「该工具是否需要 user_id」═══
    # 必须在这里判断 —— 此处拿到的是**原始函数**（decorator 里
    # `original_func = func`），签名还没被下面的 **kwargs 包装覆盖。
    #
    # 为什么不在调用侧用签名判断：`tool_obj.func` 已被包装成 `(**kwargs)`，
    # 签名检查会命中 VAR_KEYWORD → 把所有工具都误判为「接受 user_id」，
    # 给 `get_products_specs_extract(products)` 这类工具塞进 user_id，
    # 触发 `TypeError: unexpected keyword argument`（实测踩坑）。
    #
    # 为什么不用 args_schema 判断：schema 只声明「给模型看的参数」，
    # find_archive / save_to_archive 的 user_id 不在 schema 里
    # （由 runtime 注入，不该让模型填），用 schema 判断会误排除它们。
    try:
        import inspect as _inspect

        _params = _inspect.signature(original_func).parameters
        tool_obj._sc_needs_user_id = "user_id" in _params
    except (TypeError, ValueError):
        tool_obj._sc_needs_user_id = False

    async def runtime_wrapper(**kwargs: Any) -> Any:
        """所有工具的统一执行入口。"""
        from src.agents.common.toolkits.runtime import get_runtime

        runtime = get_runtime()
        result = await runtime.execute(
            tool_name=tool_name,
            tool_func=original_func,
            args=kwargs,
            handlers=custom_handlers,
        )
        return result.to_agent_message()

    def sync_runtime_wrapper(**kwargs: Any) -> Any:
        """同步入口：委托给异步版本。"""
        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(runtime_wrapper(**kwargs))
        else:
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, runtime_wrapper(**kwargs))
                return future.result(timeout=300)

    # 挂载到 LangChain StructuredTool 上
    tool_obj.func = sync_runtime_wrapper
    tool_obj.coroutine = runtime_wrapper
