import asyncio
import logging
from typing import NotRequired, Annotated
from langchain.agents.middleware.types import AgentMiddleware, AgentState, PrivateStateAttr
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime


class IntentDetectorState(AgentState):
    """
    注册进 LangGraph 状态机的意图字段。
    PrivateStateAttr 表示不向父 Agent 传播（子 Agent 独立识别自己的意图）。
    如果需要 MasterAgent 读取，去掉 PrivateStateAttr。
    """
    intent: NotRequired[Annotated[dict, PrivateStateAttr]]


class IntentDetectorMiddleware(AgentMiddleware):
    """意图识别中间件

    在 before_agent 阶段调用 JointIntentService，将结果写入 state.intent
    """

    name = "intent_detector"
    state_schema = IntentDetectorState  # 必须有，不能是 None

    def __init__(self, confidence_threshold: float = 0.6):
        self._threshold = confidence_threshold

    # 同步版（兼容 factory.py 的同步调用路径）
    def before_agent(self, state: dict, runtime: Runtime) -> dict | None:
        text = self._get_last_human_text(state)
        if not text:
            return None
        if self._should_skip(state, text):
            return None

        try:
            from src.services.intent_service import get_intent_service
            intent_result = get_intent_service().predict(text, self._threshold)
            return {"intent": intent_result}
        except Exception as e:
            # torch 未安装或模型加载失败时跳过意图识别
            logging.debug(f"[IntentDetector] Intent detection failed ({type(e).__name__}: {e}), skipping")
            return None

    # 异步版（stream_messages 走的是这个）
    async def abefore_agent(self, state: dict, runtime: Runtime) -> dict | None:
        import logging
        logging.info(f"[IntentDetector] >>> 进入 abefore_agent")
        text = self._get_last_human_text(state)
        logging.info(f"[IntentDetector] 提取到的文本: {text[:50] if text else None}...")

        if not text:
            logging.warning("[IntentDetector] 未找到 HumanMessage，跳过意图识别")
            return None

        if self._should_skip(state, text):
            return None

        try:
            from src.services.intent_service import get_intent_service
            logging.info(f"[IntentDetector] 开始调用意图识别服务...")
            intent_result = await asyncio.to_thread(
                get_intent_service().predict, text, self._threshold
            )
            logging.info(f"[IntentDetector] 意图: {intent_result['main_intent']} | 置信度: {intent_result['intent_confidence']:.3f} | 缺失槽位: {intent_result.get('missing_slots', [])}")
            return {"intent": intent_result}
        except Exception as e:
            # torch 未安装或模型加载失败时跳过意图识别
            logging.error(f"[IntentDetector] Intent detection failed ({type(e).__name__}: {e})", exc_info=True)
            return None

    @staticmethod
    def _get_last_human_text(state: dict) -> str | None:
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                return msg.content if isinstance(msg.content, str) else None
        return None

    @staticmethod
    def _should_skip(state: dict, current_text: str) -> bool:
        """仅当 state 中的 raw_input 与当前输入完全一致时才跳过（避免 stale intent）"""
        existing_intent = state.get("intent") or {}
        existing_raw = existing_intent.get("raw_input", "")
        if existing_raw and existing_raw == current_text:
            logging.info(f"[IntentDetector] intent raw_input 与当前输入一致，跳过重复识别")
            return True
        logging.info(f"[IntentDetector] 检测到新输入 (raw_input='{existing_raw}' -> '{current_text[:30]}...')，重新识别意图")
        return False
