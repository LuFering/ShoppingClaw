"""送礼智能体（gift）—— 独立于主智能体的 agent。

与 planning 是**并列**关系：共用服务模式，不共用业务逻辑。

  采购 = 决策收敛：N 个候选 → 1 个方案，核心产物是决策图
  送礼 = 意义建构：1 个意图 → 一段过程 → 1 份礼物，核心产物是人物档案

产品上的三条硬约束（见 `web-v2/.impeccable.md` 的「分区豁免」）：
  1. 页面高度恒定一屏，步骤进覆盖层
  2. 叙事区不许变成可增长的列表
  3. 每处推荐与每处替换都必须可解释 —— 不是参数可解释，是心意可解释

目录：agent.py / graph.py / context.py / stages.py / prompts/ / skills/
"""

from src.agents.independent.gift.agent import GiftAgent  # noqa: F401

__all__ = ["GiftAgent"]
