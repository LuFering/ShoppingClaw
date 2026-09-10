"""动态模型切换中间件

允许每个请求通过运行时 context.model（格式 "provider/model"）覆盖智能体模型。
图在构图时烘焙的模型仅作为兜底；本中间件在每次模型调用前按 context 重新解析，
解析失败时降级为默认模型并记 warning，绝不中断对话。
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
        from src.agents.common.models import load_chat_model

        request.model = load_chat_model(requested_model)
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
        return await handler(request)
