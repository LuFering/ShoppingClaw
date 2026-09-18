"""动态模型切换中间件

允许每个请求通过运行时 context.model（格式 "provider/model"）覆盖智能体模型。
图在构图时烘焙的模型仅作为兜底；本中间件在每次模型调用前按 context 重新解析，
解析失败时降级为默认模型并记 warning，绝不中断对话。

此外还承担「限额熔断」职责：若请求指定的模型在调用时抛出配额/欠费/限流类错误
（429 insufficient_quota、402 Insufficient Balance、tpm/rpm 超限等），会立刻把
该模型记入熔断名单，并在本次请求内**当场换用默认模型重试一次**。

为什么必须在这里重试：前端的模型选择器把用户选的模型写进 localStorage 并随每次
请求发送。一旦那个模型欠费，整条 SSE 流会在第一次 model 调用处直接终止 —— 前端
只显示一句问候语，所有工具卡 / 编排卡 / 子智能体卡全部不出现，看起来就像"前端
设计丢了"。当场回退 + 后续熔断，可以保证用户无论选了什么模型都能拿到完整结果。
"""
import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import ModelRequest, ModelResponse, StateT
from langgraph.runtime import Runtime
from langgraph.typing import ContextT

logger = logging.getLogger(__name__)


def _resolve_model(request: ModelRequest[ContextT]) -> None:
    """按运行时 context.model 覆盖 request.model；解析失败仅记 warning。"""
    context = getattr(request.runtime, "context", None)
    requested_model = getattr(context, "model", None)

    if not requested_model:
        return

    try:
        from src.agents.common.llm import load_chat_model_with_fallback

        resolved, actual = load_chat_model_with_fallback(requested_model)
        request.model = resolved
        if actual != requested_model:
            logger.warning(
                f"[DynamicModel] 请求模型 {requested_model} 已熔断，"
                f"本次改用 {actual}"
            )
        else:
            logger.info(f"[DynamicModel] 使用请求指定模型: {requested_model}")
    except Exception as e:
        logger.warning(
            f"[DynamicModel] 加载模型 {requested_model} 失败，"
            f"回退默认模型: {type(e).__name__}: {e}"
        )


class DynamicModelMiddleware(AgentMiddleware):
    name = "dynamic_model"

    async def awrap_model_call(self, request, handler):
        _resolve_model(request)
        try:
            return await handler(request)
        except Exception as e:
            from src.agents.common.llm import (
                is_quota_error,
                load_chat_model,
                mark_model_unavailable,
            )

            if not is_quota_error(e):
                raise

            context = getattr(request.runtime, "context", None)
            requested_model = getattr(context, "model", None) or ""
            current_spec = getattr(request.model, "model_name", None) or getattr(
                request.model, "model", ""
            )
            mark_model_unavailable(
                requested_model or str(current_spec), f"{type(e).__name__}: {e}"
            )

            from src.config import config as _cfg

            fallback_spec = _cfg.default_model
            if fallback_spec and fallback_spec != requested_model:
                logger.warning(
                    f"[DynamicModel] 模型 {requested_model} 配额/限流异常，"
                    f"本次请求当场回退到 {fallback_spec} 重试"
                )
                try:
                    request.model = load_chat_model(fallback_spec)
                    return await handler(request)
                except Exception as e2:
                    logger.error(f"[DynamicModel] 回退模型 {fallback_spec} 仍失败: {e2}")
                    raise e2 from e
            raise
