"""采购规划智能体（planning）—— 独立于主智能体的 agent。

与主智能体的关系（两套，不是一套）：
  · 它有自己的编排（本目录的图）、自己的工具集、自己的技能库
  · 它**不被** `agent_manager` 自动发现 —— 注册是显式的（见 agent.py）
  · 将来若要被主智能体当普通子智能体调用，是「同一套定义的另一种挂载」：
    把 system_prompt + 工具清单作为一条 subagents.yaml 条目即可，代码不用改

目录约定（与项目其余部分一致）：
  agent.py      BaseAgent 子类 —— 对外入口
  graph.py      LangGraph 状态图 —— 阶段节点串成链
  context.py    运行时上下文（BaseContext 子类）
  stages.py     各阶段的**实现**（取数、RAG、图变更）
  prompts/      系统提示词
  skills/       技能库（SKILL.md）
"""

from src.agents.independent.planning.agent import PlanningAgent  # noqa: F401

__all__ = ["PlanningAgent"]
