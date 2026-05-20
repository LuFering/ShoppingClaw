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
        self._reply_generated = False  # 标记是否已生成过回复
    
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
        
        # 追问阶段：意图明确但有missing_slots，需等待用户补充槽位
        intent_confidence = intent.get("intent_confidence", 0)
        missing_slots = intent.get("missing_slots", [])
        last_message = state.get("messages", [])[-1] if state.get("messages") else None

        if intent_confidence >= 0.6 and missing_slots:
            # LLM 已生成追问回复（有实质性内容），直接放行给用户
            if last_message and hasattr(last_message, 'content') and last_message.content and len(str(last_message.content)) > 20:
                logging.info(f"[GapDetector] LLM已生成追问内容({len(str(last_message.content))}字符)，直接放行")
                return {
                    "gap": {"decision_confidence": 0.5, "information_gaps": ["user_slot_required"]},
                    "jump_to": None
                }
            # LLM 未生成追问回复，跳回 model 让 LLM 生成追问
            logging.info(f"[GapDetector] missing_slots存在但LLM未生成追问，跳回model")
            return {
                "gap": {"decision_confidence": 0.5, "information_gaps": ["user_slot_required"]},
                "jump_to": "model"
            }
        
        # LLM调度决策豁免：LLM已经决定调用SubAgent，信任其判断
        # 注意：after_model 执行时 messages[-1] 是 LLM 的 AIMessage（包含 tool_calls）
        if last_message and hasattr(last_message, 'tool_calls') and last_message.tool_calls:
            logging.info(f"\n[GapDetector] 检测到LLM已调度工具调用（{len(last_message.tool_calls)}个），设置jump_to=tools")
            return {
                "gap": {"decision_confidence": 1.0, "information_gaps": []},
                "jump_to": "tools"
            }
        
        # 问候语意图直接放行，无需补证
        main_intent = intent.get("main_intent", "")
        if main_intent == "greeting":
            # 调试：打印最后一条消息的结构
            if last_message:
                import logging
                logging.info(f"[GapDetector] 最后一条消息类型: {type(last_message).__name__}")
                logging.info(f"[GapDetector] 是否有 tool_calls: {hasattr(last_message, 'tool_calls') and bool(last_message.tool_calls)}")
                if hasattr(last_message, 'content'):
                    content_preview = str(last_message.content)[:100]
                    logging.info(f"[GapDetector] 内容预览: {content_preview}")
            
            logging.info(f"[GapDetector] 问候语意图，直接放行")
            return {
                "gap": {"decision_confidence": 1.0, "information_gaps": ["no_gap"]},
                "jump_to": "end"  # 直接结束，输出 LLM 已生成的回复
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
            # 证据充足，检查模型是否已经生成了回复
            if last_message and hasattr(last_message, 'content') and last_message.content and len(str(last_message.content)) > 20:
                # 模型已生成实质性回复，直接结束
                logging.info(f"[GapDetector] 证据充足且回复已生成({len(str(last_message.content))}字符)，结束对话")
                return {
                    "gap": result,
                    "information_gaps": ["no_gap"],
                    "decision_confidence": result["decision_confidence"],
                    "jump_to": "end"
                }
            else:
                # 模型尚未生成回复，跳回 model 生成
                logging.info(f"[GapDetector] 证据充足但无回复内容，跳回model生成")
                update["jump_to"] = "model"
        
        return update
