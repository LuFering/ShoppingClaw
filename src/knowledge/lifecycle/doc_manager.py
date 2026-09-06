import logging
from pathlib import Path

from ..core.models import SourceType
from ..indexers.markdown_indexer import MarkdownIndexer
from ..stores.faq_store import FAQStore
from ..stores.rule_engine import RuleEngine
from ..stores.vector_store import VectorStore

logger = logging.getLogger(__name__)

_RULE_TYPES = {SourceType.POLICY, SourceType.RISK_CONTROL}
_VECTOR_TYPES = {SourceType.FRAMEWORK, SourceType.EXPERIENCE}
_FAQ_TYPES = {SourceType.FAQ}


class DocManager:
    def __init__(
        self,
        rule_engine: RuleEngine,
        vector_store: VectorStore,
        faq_store: FAQStore,
    ) -> None:
        self._rule = rule_engine
        self._vec = vector_store
        self._faq = faq_store
        self._indexer = MarkdownIndexer()

    async def upsert_file(self, path: str | Path) -> int:
        items = self._indexer.index_file(path)
        if not items:
            return 0

        doc_id = items[0].doc_id
        await self._delete_doc(doc_id)

        rule_items = [item for item in items if item.source_type in _RULE_TYPES]
        vector_items = [item for item in items if item.source_type in _VECTOR_TYPES]
        faq_items = [item for item in items if item.source_type in _FAQ_TYPES]

        if rule_items:
            await self._rule.add(rule_items)
        if vector_items:
            await self._vec.add(vector_items)
        if faq_items:
            await self._faq.add(faq_items)

        logger.info("[DocManager] upsert %s: %s chunks", path, len(items))
        return len(items)

    async def upsert_directory(self, dir_path: str | Path) -> int:
        root = Path(dir_path)
        if not root.exists():
            logger.warning("[DocManager] directory not found: %s", dir_path)
            return 0

        total = 0
        for md_file in sorted(root.rglob("*.md")):
            total += await self.upsert_file(md_file)
        return total

    async def _delete_doc(self, doc_id: str) -> None:
        await self._rule.delete_by_doc_id(doc_id)
        await self._vec.delete_by_doc_id(doc_id)
        await self._faq.delete_by_doc_id(doc_id)
