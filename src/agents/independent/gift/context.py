"""送礼智能体的运行时上下文。"""
from dataclasses import dataclass, field
from pathlib import Path

from src.agents.common.context import BaseContext

_PROMPT = Path(__file__).parent / "prompts" / "system.md"
GIFT_SYSTEM_PROMPT = _PROMPT.read_text(encoding="utf-8") if _PROMPT.exists() else "你是送礼顾问。"


@dataclass
class GiftContext(BaseContext):
    """一次送礼推演的上下文。

    与 PlanningContext 的区别：这里没有「场景/约束」，
    有的是**收礼人**与**在意点** —— 送礼的输入是人，不是需求。
    """

    system_prompt: str = field(
        default=GIFT_SYSTEM_PROMPT,
        metadata={
            "__template_metadata__": {"kind": "prompt"},
            "name": "系统提示词",
            "description": "送礼顾问的角色、边界与技能路由表",
        },
    )

    recipient: str = field(default="", metadata={"name": "送给谁", "description": "如「妈妈」"})
    occasion: str = field(default="", metadata={"name": "为了什么", "description": "如「生日」"})
    budget: int = field(default=0, metadata={"name": "预算", "description": "单位：元"})
    signals: list[str] = field(
        default_factory=list,
        metadata={"name": "在意点", "description": "如 ['实用', '有心意']"},
    )
    run_id: str | None = field(default=None, metadata={"name": "任务实例 ID"})
