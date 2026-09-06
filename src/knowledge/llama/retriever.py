"""LlamaIndex 检索器 — 基于 VectorStoreIndex + MetadataFilters 检索并转 KnowledgeItem。

metadata 过滤下推到 Chroma 的 where（source_type IN / category EQ），
而不是取回再删，保证过滤发生在向量库层面。
"""

from __future__ import annotations

import logging

from llama_index.core.vector_stores import (
    FilterCondition,
    FilterOperator,
    MetadataFilter,
    MetadataFilters,
)

from ..core.models import KnowledgeItem, SourceType

logger = logging.getLogger(__name__)


class LlamaRetriever:
    """LlamaIndex 语义检索适配器（同步实现，调用方以 to_thread 包裹）。

    基于 LlamaIndex 单路向量检索，不再需要多后端统一抽象。
    """

    def __init__(self, indexer) -> None:
        self._indexer = indexer

    def retrieve(
        self,
        query: str,
        category: str | None = None,
        source_types: list[str] | None = None,
        top_k: int = 5,
    ) -> list[KnowledgeItem]:
        index = self._indexer.index
        if index is None:
            logger.warning("[LlamaRetriever] 索引未初始化，返回空")
            return []

        filters = self._build_filters(category, source_types)
        # 多召回一些（top_k*3）再交给 ResultFuser 去重 + source_type bonus 重排
        retriever = index.as_retriever(
            similarity_top_k=max(top_k * 3, top_k),
            filters=filters,
        )

        try:
            nodes = retriever.retrieve(query)
        except Exception as exc:
            logger.warning("[LlamaRetriever] 检索失败: %s", exc)
            return []

        items = [self._to_item(node) for node in nodes]
        items.sort(key=lambda item: (-item.score, item.source_type.priority, item.doc_id))
        return items[: max(top_k * 3, top_k)]

    @staticmethod
    def _build_filters(
        category: str | None,
        source_types: list[str] | None,
    ) -> MetadataFilters | None:
        filters: list[MetadataFilter] = []

        if source_types:
            normalized = [str(s).strip().lower() for s in source_types if str(s).strip()]
            if normalized:
                filters.append(
                    MetadataFilter(
                        key="source_type",
                        value=normalized,
                        operator=FilterOperator.IN,
                    )
                )

        if category:
            cat = str(category).strip()
            if cat:
                filters.append(
                    MetadataFilter(
                        key="category",
                        value=cat,
                        operator=FilterOperator.EQ,
                    )
                )

        if not filters:
            return None
        return MetadataFilters(filters=filters, condition=FilterCondition.AND)

    @staticmethod
    def _to_item(node) -> KnowledgeItem:
        metadata = node.metadata or {}
        score = getattr(node, "score", 0.0) or 0.0
        source_type_value = str(metadata.get("source_type", "experience")).strip().lower()
        try:
            source_type = SourceType(source_type_value)
        except ValueError:
            source_type = SourceType.EXPERIENCE

        keywords = _split_csv(metadata.get("keywords"))
        tags = _split_csv(metadata.get("tags"))

        return KnowledgeItem(
            content=node.text,
            source_type=source_type,
            doc_id=str(metadata.get("doc_id") or ""),
            category=metadata.get("category") or None,
            tags=tags,
            metadata={
                "keywords": keywords,
                "source_path": metadata.get("source_path"),
                "section_title": metadata.get("section_title") or metadata.get("header_path"),
                "section_path": metadata.get("header_path"),
                "question": metadata.get("question"),
                "distance": max(1.0 - score, 0.0),
            },
            chunk_id=metadata.get("chunk_id") or getattr(node, "node_id", None),
            score=score,
            title=metadata.get("title") or metadata.get("section_title"),
            retriever="llama_chroma",
        )


def _split_csv(value) -> list[str]:
    if not value:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]
