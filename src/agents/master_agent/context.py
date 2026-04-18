from dataclasses import dataclass, field
from pathlib import Path

from src.agents.common.context import BaseContext
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
            "description":"MainAgent的角色和行为指导",
        },
    )

    subagents_model:str=field(
        default="ollama/qwen2.5:3b",
        metadata={
            "name":"Sub-agent Model",
            "description":"子智能体，供主智能体调用",
        },
    )