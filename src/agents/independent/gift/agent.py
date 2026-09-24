"""送礼智能体 —— `BaseAgent` 子类。

**显式注册**（在 `src/agents/__init__.py` 里），与 PlanningAgent 同法。
注册后自动获得 `/api/chat/agent` 列表与 SSE 对话入口，
但它的主界面是 `/proxy` 工作台，走 `/api/gift/runs/*` 那套任务实例接口。

将来被主智能体当普通子智能体调用时，是「同一套定义的另一种挂载」——
把 system_prompt + 工具清单作为一条 subagents.yaml 条目即可，代码不用改。
"""
from __future__ import annotations

import logging
from pathlib import Path

from src.agents.common.base import BaseAgent
from src.agents.independent.gift.context import GiftContext
from src.agents.independent.gift.graph import get_gift_graph

logger = logging.getLogger(__name__)


class GiftAgent(BaseAgent):
    """送礼顾问：先理解人，再决定送什么；每处推荐都说得清为什么。"""

    name = "送礼顾问"
    description = "给一个人挑一份说得通的礼物 —— 先理解关系，再组合心意"
    context_schema = GiftContext
    capabilities = ["送礼推荐", "礼物组合", "心意解读", "寄语文案"]

    examples = [
        "妈妈生日送什么，预算 800",
        "同事离职，送一份不太贵重但用心的",
        "她什么都不缺，想送点有意义的",
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_graph(self, **kwargs):
        """图是无状态的（不挂 checkpointer）：run 状态落在 `gift_runs` 表，
        断点续跑由 gift_service 按步骤推进 —— 那样刷新页面才不会断。"""
        if self.graph is None:
            self.graph = get_gift_graph()
        return self.graph


def get_skills_dir() -> Path:
    """技能库目录 —— 供 SkillsMiddleware 用 FilesystemBackend 挂载。"""
    return Path(__file__).parent / "skills"
