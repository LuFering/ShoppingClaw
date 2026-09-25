"""采购规划智能体 —— `BaseAgent` 子类，对外入口。

**显式注册，不自动发现**：`agent_manager` 的 `auto_discover_agent()` 至今是
空实现（`src/agents/__init__.py`），所有 agent 都是手动 `register_agent`。
本类沿用同一做法，注册行写在 `src/agents/__init__.py` 里。

注册后自动获得的能力（无需额外代码）：
  · `GET /api/chat/agent` 会列出它
  · `POST /api/chat/agent/{name}` 的 SSE 对话流可用（`chat_stream_service` 按名取实例）

但它**不主要靠通用对话入口**：采购规划的主界面是工作台，走
`/api/planning/runs/*` 那套任务实例接口。通用对话入口留着是为了
「被主智能体当子智能体调用」那条路（见模块 docstring 末段）。
"""
from __future__ import annotations

import logging
from pathlib import Path

from src.agents.common.base import BaseAgent
from src.agents.independent.planning.context import PlanningContext
from src.agents.independent.planning.graph import get_planning_agent

logger = logging.getLogger(__name__)


class PlanningAgent(BaseAgent):
    """采购规划顾问：自己编排工具、自己决定什么时候给结论。

    与主智能体的关系是**并列**的，不是上下级：
      · 有独立的 agent（ReAct 循环）与工具集（`tools.py`）
      · 有独立的技能库（`skills/`，经 SkillsMiddleware 挂载）
      · 复用底层工具与 MCP/RAG 机制（不重复造取数链路）
    """

    name = "采购规划"
    description = "装修、换季、搬家的组合采购 —— 拆清单、排顺序、盯依赖"
    context_schema = PlanningContext
    capabilities = ["采购规划", "组合采购", "清单拆解", "预算分配"]

    # 前端 AgentManageView 的示例问法（get_info 会读它）
    examples = [
        "三居室装修要买哪些家电，预算 8 万",
        "搬家置办，先买什么后买什么",
        "换季买冬装，按家庭成员分工列个清单",
    ]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    async def get_graph(self, **kwargs):
        """返回编译好的 agent（ReAct 循环）。

        图是**无状态**的（不挂 checkpointer）：run 的状态落在
        `planning_runs` 表里，中断/续跑由 `planning_service` 管
        —— 挂 thread 机制的话刷新页面就断了。
        """
        if self.graph is None:
            self.graph = get_planning_agent()
        return self.graph

    async def get_info(self) -> dict:
        info = await super().get_info()
        info["configurable_items"] = []
        return info


def get_skills_dir() -> Path:
    """技能库目录 —— 供 SkillsMiddleware 用 FilesystemBackend 挂载。"""
    return Path(__file__).parent / "skills"
