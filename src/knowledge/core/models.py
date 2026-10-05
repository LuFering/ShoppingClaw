from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SourceType(str, Enum):
    """Supported knowledge source types."""

    POLICY = "policy"
    RISK_CONTROL = "risk_control"
    FRAMEWORK = "framework"
    EXPERIENCE = "experience"
    FAQ = "faq"

    @property
    def prefix(self) -> str:
        prefix_map = {
            SourceType.POLICY: "[官方规则]",
            SourceType.RISK_CONTROL: "[风控提醒]",
            SourceType.FRAMEWORK: "[决策标准]",
            SourceType.FAQ: "[常见问题]",
            SourceType.EXPERIENCE: "[经验结论]",
        }
        return prefix_map[self]

    @property
    def priority(self) -> int:
        priority_map = {
            SourceType.POLICY: 0,
            SourceType.RISK_CONTROL: 1,
            SourceType.FRAMEWORK: 2,
            SourceType.FAQ: 3,
            SourceType.EXPERIENCE: 4,
        }
        return priority_map[self]


@dataclass(slots=True)
class KnowledgeItem:
    """Normalized knowledge payload shared across indexers and retrievers."""

    content: str
    source_type: SourceType
    doc_id: str
    category: str | None = None
    tags: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    chunk_id: str | None = None
    score: float = 0.0
    title: str | None = None
    retriever: str | None = None

    def dedupe_key(self) -> str:
        # 按 **doc_id** 去重，而不是 chunk_id。
        #
        # 为什么改：同一篇文档会被切成多个 chunk，每个 chunk 有自己的
        # chunk_id。原先按 chunk_id 去重等于不去重 —— 实测 sop_gift
        # 一次返回 3 遍（同文档 3 个 chunk 全进 top_k），把名额占满、
        # 挤掉其他相关文档。
        #
        # 按 doc_id 去重后，同一篇文档只保留得分最高的那个 chunk。
        # 代价是丢掉同文档其他片段的信息 —— 但 top_k 通常只有 3，
        # 覆盖多篇文档比深挖一篇更有价值。
        if self.doc_id:
            return self.doc_id
        normalized_title = (self.title or "").strip().lower()
        normalized_content = self.content.strip().lower()
        return f"{self.source_type.value}::{normalized_title}::{normalized_content}"
