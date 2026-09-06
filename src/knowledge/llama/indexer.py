"""LlamaIndex 索引器 — 灌入 Markdown 知识并持久化到 ChromaDB。

核心职责：
- MarkdownNodeParser 按标题切分，doc 级 metadata 自动传播到 node
- 稳定 node_id（uuid5），保证 upsert 幂等去重
- ChromaVectorStore 落盘，collection 名 shoppingclaw_kb
- load_or_build：已有数据直接 from_vector_store 复用，否则从文档构建
"""

from __future__ import annotations

import hashlib
import logging
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from llama_index.core import Settings, StorageContext, VectorStoreIndex
from llama_index.core.node_parser import MarkdownNodeParser, SentenceSplitter
from llama_index.core.schema import Document
from llama_index.vector_stores.chroma import ChromaVectorStore

from ..core.models import SourceType

logger = logging.getLogger(__name__)

DEFAULT_COLLECTION = "shoppingclaw_kb"


class LlamaIndexer:
    """基于 LlamaIndex + ChromaDB 的知识索引器。"""

    def __init__(
        self,
        persist_dir: str,
        embed_model=None,
        collection: str = DEFAULT_COLLECTION,
        chunk_size: int = 900,
        chunk_overlap: int = 120,
    ) -> None:
        self._persist_dir = Path(persist_dir)
        self._persist_dir.mkdir(parents=True, exist_ok=True)
        self._collection_name = collection
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._embed_model = embed_model
        self._index: VectorStoreIndex | None = None

        if embed_model is not None:
            Settings.embed_model = embed_model  # 注意：必须赋值式，构造式会被静默忽略

        self._setup_vector_store()

    # ── Chroma 初始化 ──────────────────────────────────────────

    def _setup_vector_store(self) -> None:
        import chromadb
        from chromadb.config import Settings as ChromaSettings

        client = chromadb.PersistentClient(
            path=str(self._persist_dir),
            settings=ChromaSettings(anonymized_telemetry=False),
        )
        collection = client.get_or_create_collection(
            name=self._collection_name,
            metadata={"hnsw:space": "cosine"},
        )
        self._vector_store = ChromaVectorStore(chroma_collection=collection)
        self._storage_context = StorageContext.from_defaults(vector_store=self._vector_store)

    # ── 索引构建 / 复用 ─────────────────────────────────────────

    @property
    def index(self) -> VectorStoreIndex | None:
        """懒加载：已有索引直接返回，未初始化返回 None。"""
        return self._index

    def load_or_build(self, documents: list[Document] | None) -> VectorStoreIndex | None:
        """已有向量库则复用（免重灌），否则用 documents 构建。"""
        if self._embed_model is None:
            logger.warning("[LlamaIndexer] 无 embedding 模型，跳过索引加载/构建")
            return None

        # 优先复用已持久化的 Chroma 集合
        if self._vector_store_count() > 0:
            try:
                self._index = VectorStoreIndex.from_vector_store(
                    self._vector_store, embed_model=self._embed_model
                )
                logger.info("[LlamaIndexer] 复用已有 Chroma 集合 %s", self._collection_name)
                return self._index
            except Exception as exc:
                logger.warning("[LlamaIndexer] 复用索引失败，转为重建: %s", exc)

        if documents:
            return self.build(documents)
        return None

    def build(self, documents: list[Document]) -> VectorStoreIndex | None:
        """从 Document 列表构建索引并落盘。"""
        if self._embed_model is None:
            logger.warning("[LlamaIndexer] 无 embedding 模型，跳过构建")
            return None
        nodes = self._parse_to_nodes(documents)
        if not nodes:
            logger.warning("[LlamaIndexer] 切分后无有效 node，跳过构建")
            return None
        # 空 vector store 上建 index，再批量插入 nodes（落盘到 Chroma）
        self._index = VectorStoreIndex.from_vector_store(
            self._vector_store, embed_model=self._embed_model
        )
        self._index.insert_nodes(nodes)
        logger.info("[LlamaIndexer] 构建完成，共 %d nodes", len(nodes))
        return self._index

    def ingest_directory(self, docs_dir: str | Path) -> int:
        """灌入目录下所有文档，返回 node 数。"""
        from .loader import load_markdown_documents

        documents = load_markdown_documents(docs_dir)
        if not documents:
            return 0
        if self._vector_store_count() > 0:
            self._clear_collection()
        return self._ingest_documents(documents)

    def ingest_file(self, md_file: str | Path) -> int:
        """灌入单个 Markdown 文件，返回 node 数。"""
        from .loader import _load_file

        doc = _load_file(Path(md_file))
        if doc is None:
            return 0
        return self._ingest_documents([doc])

    def _ingest_documents(self, documents: list[Document]) -> int:
        nodes = self._parse_to_nodes(documents)
        if not nodes:
            return 0
        # 追加模式：基于现有 index 或重建
        if self._index is None:
            if self._vector_store_count() > 0:
                self.load_or_build(None)
            else:
                self._index = VectorStoreIndex.from_vector_store(
                    self._vector_store, embed_model=self._embed_model
                )
        self._index.insert_nodes(nodes)
        logger.info("[LlamaIndexer] 灌入 %d nodes", len(nodes))
        return len(nodes)

    # ── 删除 / 清空 ─────────────────────────────────────────────

    def delete_doc(self, doc_id: str) -> int:
        """删除某个 doc_id 下的所有 node，返回删除数量。"""
        chroma_collection = self._collection()
        result = chroma_collection.get(where={"doc_id": doc_id})
        ids = result.get("ids") or []
        if ids:
            chroma_collection.delete(ids=ids)
            logger.info("[LlamaIndexer] 删除 doc_id=%s 的 %d nodes", doc_id, len(ids))
        return len(ids)

    def clear_collection(self) -> None:
        self._clear_collection()

    def _clear_collection(self) -> None:
        try:
            self._collection().delete(where={})
        except Exception as exc:
            logger.warning("[LlamaIndexer] 清空集合失败: %s", exc)
        self._index = None

    # ── 工具方法 ────────────────────────────────────────────────

    def _collection(self):
        """访问底层 Chroma collection。"""
        return self._vector_store._collection

    def _vector_store_count(self) -> int:
        try:
            return self._collection().count()
        except Exception:
            return 0

    def _parse_to_nodes(self, documents: list[Document]) -> list:
        """两段式切分：
        1. MarkdownNodeParser 按标题层级切出结构块（保留 header_path）。
        2. 对超长块（> chunk_size）用 SentenceSplitter 二次切分，控制 token 上限。
        """
        markdown_parser = MarkdownNodeParser.from_defaults()
        structural_nodes = markdown_parser.get_nodes_from_documents(documents)

        splitter = SentenceSplitter(
            chunk_size=self._chunk_size, chunk_overlap=self._chunk_overlap
        )
        final_nodes: list = []
        for snode in structural_nodes:
            # 过滤纯标题 node（内容就是文档主标题本身，信息量低）
            text = (snode.text or "").strip()
            if self._is_title_only(text):
                continue

            if self._estimate_chars(text) <= self._chunk_size:
                final_nodes.append(snode)
            else:
                sub_nodes = splitter.split_text(text)
                for sub_text in sub_nodes:
                    final_nodes.append(self._spawn_node(snode, sub_text))

        # 分配稳定 node_id + chunk_id metadata，保证 upsert 幂等
        for idx, node in enumerate(final_nodes):
            doc_id = node.metadata.get("doc_id", "")
            header = node.metadata.get("header_path", "")
            digest = hashlib.md5(node.text.encode("utf-8")).hexdigest()[:10]
            node_id = str(uuid5(NAMESPACE_URL, f"{doc_id}:{header}:{idx}:{digest}"))
            node.node_id = node_id
            node.metadata["chunk_id"] = node_id
            # 兼容旧字段名：无标题文档（如 FAQ）用 title
            if "section_title" not in node.metadata:
                node.metadata["section_title"] = node.metadata.get("title", "")
        return final_nodes

    @staticmethod
    def _spawn_node(source_node, text: str):
        """基于结构块复制一个子 node（继承 metadata，仅替换文本）。"""
        import copy

        node = copy.copy(source_node)
        node.text = text
        return node

    @staticmethod
    def _is_title_only(text: str) -> bool:
        """判断一段文本是否只是标题行（# 开头且很短，无实质内容）。"""
        stripped = text.lstrip()
        if not stripped.startswith("#"):
            return False
        lines = [line for line in stripped.splitlines() if line.strip()]
        # 全部是标题行，且去除 # 后没有实质正文
        return all(line.lstrip().startswith("#") for line in lines) and len(stripped) < 60

    @staticmethod
    def _estimate_chars(text: str) -> int:
        # 中文场景直接按字符数估算，留 1.6x 余量对齐 token 上限
        return int(len(text) * 1.6)
