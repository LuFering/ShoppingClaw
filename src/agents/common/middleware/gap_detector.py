"""Gap检测中间件"""
from typing import NotRequired, Annotated
from langchain.agents.middleware.types import AgentMiddleware, AgentState, PrivateStateAttr
from langgraph.runtime import Runtime


class GapDetectorState(AgentState):
    """Gap检测状态字段"""
    gap: NotRequired[Annotated[dict, PrivateStateAttr]]


class GapDetectorMiddleware(AgentMiddleware):
    """Gap检测中间件
    
    在after_model阶段调用GapService，检测证据缺口
    """
    
    name = "gap_detector"
    state_schema = GapDetectorState
    
    def after_model(self, state: dict, runtime: Runtime) -> dict | None:
        """同步版"""
        return self._detect_gaps(state)
    
    async def aafter_model(self, state: dict, runtime: Runtime) -> dict | None:
        """异步版"""
        return self._detect_gaps(state)
    
    def _detect_gaps(self, state: dict) -> dict | None:
        """检测证据缺口"""
        import logging
        intent = state.get("intent")
        if not intent:
            return None
        
        # 追问阶段豁免：意图明确但有missing_slots，等待用户回答
        intent_confidence = intent.get("intent_confidence", 0)
        missing_slots = intent.get("missing_slots", [])
        
        if intent_confidence >= 0.6 and missing_slots:
            return {
                "gap": {"decision_confidence": 1.0, "information_gaps": []},
                "jump_to": None
            }
        
        # LLM调度决策豁免：LLM已经决定调用SubAgent，信任其判断
        # 注意：after_model 执行时 messages[-1] 是 LLM 的 AIMessage（包含 tool_calls）
        last_message = state.get("messages", [])[-1] if state.get("messages") else None
        if last_message and hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logging.info(f"\n[GapDetector] 检测到LLM已调度工具调用（{len(last_message.tool_calls)}个），设置jump_to=tools")
            return {
                "gap": {"decision_confidence": 1.0, "information_gaps": []},
                "jump_to": "tools"
            }
        
        # LLM追问豁免：意图置信度在灰色地带(0.6-0.75)且LLM选择追问用户
        if 0.6 <= intent_confidence < 0.75 and last_message and not (hasattr(last_message, 'tool_calls') and last_message.tool_calls):
            content = getattr(last_message, 'content', '')
            if content and len(content) > 20:  # 有实质性回复内容
                return {
                    "gap": {"decision_confidence": 1.0, "information_gaps": []},
                    "jump_to": None
                }
        
        # 调用Gap服务
        from src.services.gap.service import get_gap_service
        result = get_gap_service().predict(state)
        
        logging.info(f"[GapDetector] 缺口: {result['information_gaps']} | 置信度: {result['decision_confidence']:.3f}")
        
        # 构建更新
        update = {
            "gap": result,
            "information_gaps": result["information_gaps"],
            "decision_confidence": result["decision_confidence"]
        }
        
        # 熔断机制：检查是否已经尝试过太多次补证
        current_turns = state.get("turn_index", 0)
        current_turns += 1
        update["turn_index"] = current_turns
        if result["decision_confidence"] < 0.7:
            if current_turns >= 3:
                logging.info(f"[GapDetector] 达到最大补证轮次 ({current_turns})，强制放行")
                update["jump_to"] = None
            else:
                update["jump_to"] = "model"
                logging.info(f"[GapDetector] 证据不足，跳回model (当前轮次: {current_turns})")
        else:
            update["jump_to"] = None
        
        return update
