"""意图识别状态模型"""
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class IntentState:
    """意图识别结果"""
    raw_input: str = ""
    main_intent: str = "unknown"
    sub_intent: Optional[str] = None
    slots: dict = field(default_factory=dict)
    missing_slots: list = field(default_factory=list)
    intent_confidence: float = 0.0
    clarification_needed: bool = False
