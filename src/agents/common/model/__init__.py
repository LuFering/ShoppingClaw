"""子智能体输出协议（Pydantic Schema）。

各 SubAgent 的唯一合法输出形式，供两处消费：
  · src/agents/common/middleware/subagents.py  —— 输出格式校验 + 宽松回退
  · src/agents/subagents/factory.py            —— with_structured_output 强约束

★ 修复（2026-09-18）：`model/__init__.py` 原先是空文件，而上面两处都写
  `from agents.common.model import ResearcherOutput, ...`（少了 `src.` 前缀），
  于是 ImportError 被 except 静默吞掉 → `structured_model = model`（无结构化约束）
  → 子智能体返回自由文本，`_validate_output` 永远拿不到 schema 直接放行。
  这里把 schema 显式 re-export，让两条链路都真正生效。
"""
from src.agents.common.model.subagent_schemas import (  # noqa: F401
    ResearcherData,
    ResearcherOutput,
    DimensionScore,
    AnalystProductItem,
    AnalystData,
    AnalystOutput,
    RiskItem,
    CriticData,
    CriticOutput,
    PreferenceSignal,
    MemoryData,
    MemoryOutput,
)
from src.agents.common.model.product import Product  # noqa: F401

__all__ = [
    "ResearcherData",
    "ResearcherOutput",
    "DimensionScore",
    "AnalystProductItem",
    "AnalystData",
    "AnalystOutput",
    "RiskItem",
    "CriticData",
    "CriticOutput",
    "PreferenceSignal",
    "MemoryData",
    "MemoryOutput",
    "Product",
]
