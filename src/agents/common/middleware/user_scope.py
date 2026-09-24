"""user_id 注入：让子智能体的用户态工具自动拿到当前会话的用户。

问题（2026-09-22 冒烟暴露）：
  购后助手的 8 个工具（get_user_shopping_context / save_user_preference /
  recall_past_decisions / get_user_profile / save_to_archive /
  update_record_phase / set_reminder / write_review）都以 user_id 为必填参数。
  但主智能体**不会**把 user_id 写进 task description —— BASE_PROMPT 明确
  禁止在 description 里指定字段（「零过程指导原则」）。于是子智能体要么漏传、
  要么瞎编，工具必然失败：实测 `input_value={'user_id': None, ...}`，
  save_to_archive 被调用了但库里 0 条记录。

修法：
  1. `task` 工具在调用子智能体前，从 runtime.context 取出真实 user_id，
     写入 contextvar（CURRENT_USER_ID）。
  2. 子智能体拿到的用户态工具被包一层：若调用时没传 user_id（或传空），
     自动从 contextvar 补齐。

  为什么用 contextvar 而不是改工具签名：工具签名是契约的一部分，
  改签名会影响 schema 校验与 LLM 看到的参数表；contextvar 对模型透明。
  `asyncio.to_thread` 会复制 context（Python 3.9+），所以同步路径也安全。
"""
from __future__ import annotations

import contextvars
import functools
import inspect
import logging
from contextlib import contextmanager
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 当前会话的用户 id；未绑定时为 None。
CURRENT_USER_ID: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "sc_current_user_id", default=None
)


@contextmanager
def bind_user_id(user_id: str | None):
    """在本作用域内绑定 user_id，退出时自动还原。"""
    token = CURRENT_USER_ID.set(user_id or None)
    try:
        yield
    finally:
        CURRENT_USER_ID.reset(token)


def _declares_user_id(tool_obj: Any) -> bool:
    """判断工具是否需要 runtime 注入 user_id。

    判据分两级（2026-09-23 定稿）：

    1. **首选**：registry 在 Runtime 包装时打的 `_sc_needs_user_id` 标记。
       那时拿到的是**原始函数**（签名还没被 `(**kwargs)` 覆盖），
       判断最准确。

    2. **兜底**：检查 args_schema（用于未走 @tool 的动态工具，如 MCP）。

    ⚠️ 不能用 `tool_obj.func` 的签名判断：它已被 Runtime 包装成 `(**kwargs)`，
       签名检查会命中 VAR_KEYWORD → 把所有工具都误判为「接受 user_id」，
       给 `get_products_specs_extract(products)` 塞进 user_id，
       触发 `TypeError: unexpected keyword argument`（实测踩坑）。

    ⚠️ 不能只用 args_schema 判断：schema 只声明「给模型看的参数」，
       `find_archive` / `save_to_archive` 的 user_id 不在 schema 里
       （由 runtime 注入，不该让模型填），用 schema 判断会误排除它们。
    """
    marked = getattr(tool_obj, "_sc_needs_user_id", None)
    if marked is not None:
        return bool(marked)

    schema = getattr(tool_obj, "args_schema", None)
    fields = getattr(schema, "model_fields", None)
    if isinstance(fields, dict):
        return "user_id" in fields
    return False


def with_user_id(tool_obj: Any) -> Any:
    """给用户态工具包一层：调用时自动补齐 user_id。

    只处理「显式声明了 user_id 且调用方未提供」的情况 ——
    调用方主动传了值就尊重它（便于将来支持代他人查询）。
    不修改工具的 args_schema，模型看到的参数表不变。
    """
    if getattr(tool_obj, "_sc_user_scoped", False):
        return tool_obj  # 已包装，避免重复

    inner_func = getattr(tool_obj, "func", None)
    inner_coro = getattr(tool_obj, "coroutine", None)

    if not _declares_user_id(tool_obj):
        return tool_obj

    def _inject(kwargs: dict) -> dict:
        """注入当前会话的 user_id —— **无条件覆盖**模型传的值。

        ⚠️ 不能用「调用方传了值就尊重」的策略：模型几乎总会自己填一个
        user_id（实测它填了字符串 "user"），那样注入就永远不生效。
        user_id 是调用上下文而非业务参数，模型无权决定「我是谁」；
        无条件覆盖同时消除了模型编造 id 导致数据写错用户的风险。

        仅当 contextvar 未绑定时才保留原值（例如工具被独立调用、
        不在 task 流程内），此时保留调用方传参是唯一可行的兜底。
        """
        uid = CURRENT_USER_ID.get()
        if not uid:
            return kwargs
        merged = dict(kwargs)
        merged["user_id"] = uid
        return merged

    if inner_func is not None:

        @functools.wraps(inner_func)
        def _sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            return inner_func(*args, **_inject(kwargs))

        tool_obj.func = _sync_wrapper

    if inner_coro is not None:

        @functools.wraps(inner_coro)
        async def _async_wrapper(*args: Any, **kwargs: Any) -> Any:
            return await inner_coro(*args, **_inject(kwargs))

        tool_obj.coroutine = _async_wrapper

    try:
        tool_obj._sc_user_scoped = True
    except Exception:
        pass
    return tool_obj
