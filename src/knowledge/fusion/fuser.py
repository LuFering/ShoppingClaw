from ..core.models import KnowledgeItem, SourceType


class ResultFuser:
    """Fuse heterogeneous retrieval results into ranked, prompt-ready text."""

    _SOURCE_BONUS = {
        SourceType.POLICY: 0.35,
        SourceType.RISK_CONTROL: 0.30,
        SourceType.FRAMEWORK: 0.22,
        SourceType.FAQ: 0.18,
        SourceType.EXPERIENCE: 0.12,
    }

    def rank(self, items: list[KnowledgeItem], top_k: int = 5) -> list[KnowledgeItem]:
        if not items:
            return []

        deduped: dict[str, KnowledgeItem] = {}
        for item in items:
            key = item.dedupe_key()
            current = deduped.get(key)
            if current is None or self._sort_score(item) > self._sort_score(current):
                deduped[key] = item

        ranked = sorted(
            deduped.values(),
            key=lambda item: (-self._sort_score(item), item.source_type.priority, item.doc_id),
        )
        return ranked[:top_k]

    def fuse(self, items: list[KnowledgeItem], top_k: int = 5, max_chars: int = 2000) -> str:
        ranked = self.rank(items, top_k=top_k)
        if not ranked:
            return ""

        parts: list[str] = []
        total = 0
        for item in ranked:
            text = self._render_item(item)
            if total and total + len(text) > max_chars:
                break
            parts.append(text)
            total += len(text)
        return "\n".join(parts)

    def _sort_score(self, item: KnowledgeItem) -> float:
        return item.score + self._SOURCE_BONUS[item.source_type]

    @staticmethod
    def _render_item(item: KnowledgeItem) -> str:
        title = (item.title or item.metadata.get("question") or "").strip()
        content = item.content.strip()
        if title and title not in content:
            content = f"{title}\n{content}"
        return f"{item.source_type.prefix} {content}"
