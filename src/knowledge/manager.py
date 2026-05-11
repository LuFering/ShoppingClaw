import asyncio
import logging
import time
from pathlib import Path

from src.config import config

from .fusion.fuser import ResultFuser
from .lifecycle.doc_manager import DocManager
from .lifecycle.eval_monitor import EvalMonitor
from .stores.faq_store import FAQStore
from .stores.rule_engine import RuleEngine
from .stores.vector_store import VectorStore

logger = logging.getLogger(__name__)

_KNOWLEDGE_DIR = "knowledge"


class KnowledgeManager:
    def __init__(self) -> None:
        persist_dir = str(Path(config.save_dir) / _KNOWLEDGE_DIR / "chroma")
        self.rule_engine = RuleEngine()
        self.vector_store = VectorStore(persist_dir=persist_dir)
        self.faq_store = FAQStore()
        self.fuser = ResultFuser()
        self.doc_manager = DocManager(self.rule_engine, self.vector_store, self.faq_store)
        self.eval_monitor = EvalMonitor()
        self._initialized = False

    async def initialize(self, docs_dir: str | Path | None = None) -> None:
        if self._initialized:
            return
        if docs_dir:
            count = await self.doc_manager.upsert_directory(docs_dir)
            logger.info("[KnowledgeManager] initialized with %s chunks from %s", count, docs_dir)
        self._initialized = True

    async def retrieve_items(
        self,
        query: str,
        category: str | None = None,
        source_types: list[str] | None = None,
        top_k: int = 5,
    ):
        start = time.monotonic()

        tasks = [
            self.rule_engine.retrieve(query, category, top_k),
            self.vector_store.retrieve(query, category, top_k),
            self.faq_store.retrieve(query, category, top_k),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        all_items = []
        for result in results:
            if isinstance(result, Exception):
                logger.warning("[KnowledgeManager] retriever error: %s", result)
                continue
            all_items.extend(result)

        if source_types:
            allowed = {source_type.strip().lower() for source_type in source_types if source_type}
            all_items = [item for item in all_items if item.source_type.value in allowed]

        ranked = self.fuser.rank(all_items, top_k=top_k)
        latency_ms = int((time.monotonic() - start) * 1000)

        await self.eval_monitor.log(
            query=query,
            category=category,
            source_types=sorted({item.source_type.value for item in ranked}),
            result_count=len(ranked),
            latency_ms=latency_ms,
            is_hit=bool(ranked),
        )
        return ranked

    async def query_knowledge(
        self,
        query: str,
        category: str | None = None,
        source_types: list[str] | None = None,
        top_k: int = 5,
    ) -> str:
        ranked = await self.retrieve_items(
            query=query,
            category=category,
            source_types=source_types,
            top_k=top_k,
        )
        return self.fuser.fuse(ranked, top_k=top_k)


knowledge_manager = KnowledgeManager()
