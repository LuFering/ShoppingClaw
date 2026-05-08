from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List, Dict

from src.agents.common.context import BaseContext
from src.models.intent_state import IntentState

BASE_AGENT_PROMPT = (Path(__file__).parent / "BASE_PROMPT.md").read_text(encoding="utf-8")

@dataclass
class MasterContext(BaseContext):
    """
       MainAgent 的上下文配置，继承自 BaseContext
       专门用于深度分析任务的配置管理
       """
    system_prompt:str=field(
        default=BASE_AGENT_PROMPT,
        metadata={
            "__template_metadata__":{"kind": "prompt"},
            "name":"系统提示词",
            "description":"MasterAgent的角色和行为指导",
        },
    )

    subagents_model:str=field(
        default="ollama/qwen2.5:3b",
        metadata={
            "name":"Sub-agent Model",
            "description":"子智能体，供主智能体调用",
        },
    )

    intent:Optional[IntentState]=field(
        default=None,
        metadata={
            "name":"意图状态",
            "description":"由Intent Detector节点填充的意图识别结果"
        }
    )

    # --- 意图与路由状态 ---
    current_intent_type: Optional[str] = field(
        default=None,
        metadata={"name": "当前意图类型", "description": "如: COMPLEX_PURCHASE, SIMPLE_QUERY"}
    )
    intent_confidence: float = field(
        default=0.0,
        metadata={"name": "意图置信度", "description": "意图分类的置信度分数 0-1"}
    )
    routing_reasoning: Optional[str] = field(
        default=None,
        metadata={"name": "路由理由", "description": "MasterAgent 决定调用哪些 SubAgent 的逻辑依据"}
    )

    # --- 决策状态机核心字段 ---
    evidence_log: list[dict] = field(
        default_factory=list,
        metadata={"name": "证据日志", "description": "已收集的证据列表，每项包含 {type, source, content, timestamp}"}
    )
    information_gaps: list[str] = field(
        default_factory=list,
        metadata={"name": "信息缺口", "description": "当前缺失的关键信息，如 ['价格数据', '用户偏好', '竞品对比']"}
    )
    decision_confidence: float = field(
        default=0.0,
        metadata={"name": "决策置信度", "description": "当前决策的置信度，<0.7触发补充收集"}
    )

    # --- SubAgent 产出物仓库 (由 Master 调度汇总) ---
    # 这些字段会在 SubAgent 执行完毕后，由 Middleware 自动更新到 State 中
    research_data: Optional[List[Dict]] = field(default=None, metadata={"name": "Researcher产出"})
    analysis_report: Optional[Dict] = field(default=None, metadata={"name": "Analyst产出"})
    risk_audit: Optional[Dict] = field(default=None, metadata={"name": "Critic产出"})
    user_profile: Optional[Dict] = field(default=None, metadata={"name": "Memory产出"})