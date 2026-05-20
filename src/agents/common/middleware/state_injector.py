"""State 注入中间件 — 将 middleware 检测结果注入到 LLM 可见的 system prompt 中

LLM 无法直接访问 LangGraph state 对象，本中间件在 before_model 阶段
将 state.intent 和 state.gap 的关键字段格式化后追加到 system prompt 末尾，
让 Agent 不用"猜"状态，而是直接看到检测结果。
"""
import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import StateT, ModelRequest
from langgraph.runtime import Runtime
from langgraph.typing import ContextT
from langchain_core.messages import SystemMessage

logger = logging.getLogger(__name__)


class StateInjectorMiddleware(AgentMiddleware):
    """在 before_model 阶段将 state 注入 system prompt"""

    name = "state_injector"

    def __init__(self, enabled: bool = True):
        super().__init__()
        self._enabled = enabled

    def before_model(
        self,
        state: StateT,
        runtime: Runtime[ContextT],
        request: ModelRequest,
    ) -> ModelRequest | None:
        if not self._enabled:
            return None

        # 注入 state 摘要到 system prompt
        if request.system_message:
            state_text = self._format_state(state)
            if state_text:
                logger.info(f"[StateInjector] 注入状态摘要 ({len(state_text)} 字符) prompt总长: {len(request.system_message.content)}")
                new_content = request.system_message.content + "\n\n" + state_text
                return ModelRequest(
                    model=request.model,
                    tools=request.tools,
                    response_format=request.response_format,
                    system_message=SystemMessage(content=new_content),
                    messages=request.messages,
                    tool_choice=request.tool_choice,
                    state=request.state,
                    runtime=request.runtime,
                )
        return None

    async def abefore_model(
        self,
        state: StateT,
        runtime: Runtime[ContextT],
        request: ModelRequest,
    ) -> ModelRequest | None:
        return self.before_model(state, runtime, request)

    @staticmethod
    def _format_state(state: dict) -> str:
        """极简状态摘要 - 仅保留决策必需的3个核心字段，附带指令"""
        intent = state.get("intent") or {}
        gap = state.get("gap") or {}

        # 只提取3个关键字段，避免LLM过度分析
        main_intent = intent.get("main_intent", "unknown")
        sub_intent = intent.get("sub_intent", "")
        conf = intent.get("intent_confidence", 0)
        missing = intent.get("missing_slots") or []
        dc = gap.get("decision_confidence", 0)
        igs = gap.get("information_gaps") or []

        # 极简格式：一行意图 + 一行置信度 + 一行缺口 + 一行指令
        intent_line = f"意图: {main_intent}" + (f" > {sub_intent}" if sub_intent else "")
        conf_line = f"置信度: 意图{conf:.0%} / 决策{dc:.0%}"

        if missing:
            gap_line = f"缺失槽位: {', '.join(missing)}"
            instruction = "→ 追问用户补齐以上必填槽位（一次不超过2个）"
        elif igs and igs != ["no_gap"]:
            gap_line = f"证据缺口: {', '.join(igs[:2])}"
            instruction = "→ 调用SubAgent补证据，不要再追问用户"
        else:
            gap_line = "无关键缺口"
            instruction = "→ 直接进入执行层：调用SubAgent或生成回复，严禁追问用户"

        return f"\n---\n{intent_line}\n{conf_line}\n{gap_line}\n{instruction}\n---"
