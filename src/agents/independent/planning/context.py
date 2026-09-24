"""采购规划智能体的运行时上下文。"""
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from src.agents.common.context import BaseContext

_PROMPT_PATH = Path(__file__).parent / "prompts" / "system.md"

PLANNING_SYSTEM_PROMPT = (
    _PROMPT_PATH.read_text(encoding="utf-8") if _PROMPT_PATH.exists() else "你是采购规划顾问。"
)


@dataclass
class PlanningContext(BaseContext):
    """一次采购规划任务的上下文。

    与 MasterContext 的区别：这里没有「派发给谁」那套路由字段 ——
    采购规划的阶段是**固定顺序**的（见 stages.STAGES），不靠 LLM 分诊。
    """

    system_prompt: str = field(
        default=PLANNING_SYSTEM_PROMPT,
        metadata={
            "__template_metadata__": {"kind": "prompt"},
            "name": "系统提示词",
            "description": "采购规划顾问的角色、边界与技能路由表",
        },
    )

    # ── 入口页收敛出的结构化参数 ──
    scene: str = field(default="", metadata={"name": "场景", "description": "装修 / 换季 / 搬家 / 开学"})
    budget: str = field(default="", metadata={"name": "总预算", "description": "保留用户原话，如「¥6万」"})
    duration: str = field(default="", metadata={"name": "周期", "description": "如「6 周」"})
    constraints: list[str] = field(
        default_factory=list,
        metadata={"name": "硬约束", "description": "如 ['有老人', '要静音']"},
    )
    subject: str = field(default="", metadata={"name": "采购主体", "description": "本次要买什么，如「洗地机」"})

    # ── 任务实例 id（与 planning_runs.id 对应）──
    run_id: Optional[str] = field(
        default=None,
        metadata={"name": "任务实例 ID", "description": "对应 planning_runs 表的一行"},
    )
