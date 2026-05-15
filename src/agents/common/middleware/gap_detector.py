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
    
    def __init__(self):
        super().__init__()
        self._turn_counter = 0
        self._fused = False
    
    def after_model(self, state: dict, runtime: Runtime) -> dict | None:
        """同步版"""
        return self._detect_gaps(state)
    
    async def aafter_model(self, state: dict, runtime: Runtime) -> dict | None:
        """异步版"""
        import logging
        logging.info(f"[GapDetector] >>> 进入 aafter_model 节点")
        try:
            result = self._detect_gaps(state)
            logging.info(f"[GapDetector] <<< 离开 aafter_model 节点, 返回: {result}")
            return result
        except Exception as e:
            logging.error(f"[GapDetector] aafter_model 异常: {type(e).__name__}: {e}", exc_info=True)
            raise
    
    def _detect_gaps(self, state: dict) -> dict | None:
        """检测证据缺口"""
        import logging
        logging.info(f"[GapDetector] _detect_gaps 开始执行")
        
        # 熔断后跳过检测，让 LLM 回复自然输出
        if self._fused:
            logging.info("[GapDetector] 已熔断，跳过检测")
            return None
        
        intent = state.get("intent")
        logging.info(f"[GapDetector] state 中的 intent: {intent}")
        
        if not intent:
            logging.warning("[GapDetector] state 中没有 intent 字段，跳过 Gap 检测")
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
        self._turn_counter += 1
        current_turns = self._turn_counter
        if result["decision_confidence"] < 0.7:
            if current_turns >= 3:
                logging.info(f"[GapDetector] 达到最大补证轮次 ({current_turns})，强制放行")
                # 进入 model 让 LLM 生成最终回复
                update["jump_to"] = "model"
                self._fused = True
            else:
                update["jump_to"] = "model"
                logging.info(f"[GapDetector] 证据不足，跳回model (当前轮次: {current_turns})")
        else:
            update["jump_to"] = None
        
        return update
