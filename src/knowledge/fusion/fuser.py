from ..core.models import KnowledgeItem, SourceType


class ResultFuser:
    """Fuse heterogeneous retrieval results into ranked, prompt-ready text."""

    # 类型加成只应作「近似同分时的微调」，不能盖过相关度。
    # 原 0.12~0.35 相对相似度差(约 0.05~0.1)过大 —— 实测「ANC/ENC 区别」查询里，
    # 耳机文档原始相似度最高(0.574)，却被 risk_control(+0.30) 挤到第 3。
    # 现按比例下调到 0.01~0.05，保证相关度为主、类型为辅。
    _SOURCE_BONUS = {
        SourceType.POLICY: 0.05,
        SourceType.RISK_CONTROL: 0.04,
        SourceType.FRAMEWORK: 0.03,
        SourceType.FAQ: 0.02,
        SourceType.EXPERIENCE: 0.01,
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
        # 带上来源文件路径，让 agent 能据此用 read_file 打开真实文件读全文
        source_path = (item.metadata.get("source_path") or "").strip()
        if source_path:
            content = f"{content}\n(来源文件: {source_path})"
        return f"{item.source_type.prefix} {content}"
