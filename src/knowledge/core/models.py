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
        if self.chunk_id:
            return self.chunk_id
        normalized_title = (self.title or "").strip().lower()
        normalized_content = self.content.strip().lower()
        return f"{self.doc_id}::{self.source_type.value}::{normalized_title}::{normalized_content}"
