import asyncio
import logging
import os
import time
from pathlib import Path

from src.config import config

from .fusion.fuser import ResultFuser
from .lifecycle.eval_monitor import EvalMonitor
from .llama.embedding import build_embed_model
from .llama.indexer import LlamaIndexer
from .llama.retriever import LlamaRetriever

logger = logging.getLogger(__name__)


class KnowledgeManager:
    """基于 LlamaIndex + ChromaDB + DashScope Embedding 的知识管理器。

    对外契约与旧实现保持一致：
      - retrieve_items(query, category, source_types, top_k) -> list[KnowledgeItem]
      - query_knowledge(query, category, source_types, top_k) -> str
    内部由 LlamaRetriever 做语义检索 + ResultFuser 融合排序 + EvalMonitor 遥测。
    """

    def __init__(self) -> None:
        persist_dir = str(Path(config.save_dir) / "knowledge" / "chroma")
        embed_model = build_embed_model()
        self._indexer = LlamaIndexer(
            persist_dir=persist_dir,
            embed_model=embed_model,
        )
        self.retriever = LlamaRetriever(self._indexer)
        self.fuser = ResultFuser()
        self.eval_monitor = EvalMonitor()
        self._initialized = False

    async def initialize(self, docs_dir: str | Path | None = None) -> None:
        """加载或构建知识索引。

        优先复用已持久化的 Chroma 集合；集合为空时从 docs_dir 灌入。
        不传 docs_dir 且无已建集合时，索引保持未初始化（检索返回空）。
        """
        if self._initialized:
            return
        if docs_dir is None:
            docs_dir = os.getenv("KNOWLEDGE_DOCS_DIR") or str(
                Path(__file__).resolve().parent.parent.parent / "docs" / "knowledge"
            )
        docs_dir = Path(docs_dir)

        if self._indexer._vector_store_count() > 0:
            await asyncio.to_thread(self._indexer.load_or_build, None)
        elif docs_dir.exists():
            from .llama.loader import load_markdown_documents

            documents = await asyncio.to_thread(load_markdown_documents, docs_dir)
            if documents:
                await asyncio.to_thread(self._indexer.build, documents)
        else:
            logger.warning("[KnowledgeManager] 知识目录不存在: %s，知识库保持为空", docs_dir)

        self._initialized = True
        count = self._indexer._vector_store_count()
        logger.info("[KnowledgeManager] initialized, collection count=%s", count)

    async def retrieve_items(
        self,
        query: str,
        category: str | None = None,
        source_types: list[str] | None = None,
        top_k: int = 5,
    ) -> list:
        """执行语义检索并融合排序，返回 KnowledgeItem 列表。"""
        start = time.monotonic()

        all_items = await asyncio.to_thread(
            self.retriever.retrieve, query, category, source_types, max(top_k * 3, top_k)
        )

        # 兜底二次过滤（LlamaIndex 已下推，这里是保险）
        if source_types:
            allowed = {str(source_type).strip().lower() for source_type in source_types if source_type}
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
        """检索并融合为可直接使用的上下文文本。"""
        ranked = await self.retrieve_items(
            query=query,
            category=category,
            source_types=source_types,
            top_k=top_k,
        )
        return self.fuser.fuse(ranked, top_k=top_k)


knowledge_manager = KnowledgeManager()
