import asyncio
import hashlib
import math
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import chromadb
from chromadb.config import Settings

from ..core.base import RetrieverBase
from ..core.models import KnowledgeItem, SourceType
from ..core.text import extract_terms, normalize_text, overlap_score


class _HashingEmbeddingFunction:
    """Lightweight local embedding to avoid runtime model downloads."""

    def __init__(self, dimensions: int = 256) -> None:
        self._dimensions = dimensions

    @staticmethod
    def name() -> str:
        return "shoppingclaw-hash-embed-v1"

    def __call__(self, input: list[str]) -> list[list[float]]:
        return [self._embed_text(text) for text in input]

    def embed_documents(self, documents: list[str] | None = None, input: list[str] | None = None) -> list[list[float]]:
        values = documents if documents is not None else input or []
        return self(values)

    def embed_query(self, query: str | list[str] | None = None, input: str | list[str] | None = None):
        value = query if query is not None else input or ""
        if isinstance(value, list):
            return [self._embed_text(item) for item in value]
        return self._embed_text(value)

    def _embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self._dimensions
        terms = extract_terms(text)
        if not terms:
            terms = list(normalize_text(text))

        for term in terms:
            digest = hashlib.md5(term.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self._dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign

        norm = math.sqrt(sum(value * value for value in vector)) or 1.0
        return [value / norm for value in vector]


class VectorStore(RetrieverBase):
    """Dense retrieval for framework and experience knowledge."""

    _SOURCE_TO_COLLECTION = {
        SourceType.FRAMEWORK: "frameworks",
        SourceType.EXPERIENCE: "experiences",
    }

    _COLLECTION_TO_SOURCE = {
        "frameworks": SourceType.FRAMEWORK,
        "experiences": SourceType.EXPERIENCE,
    }

    def __init__(self, persist_dir: str):
        self._persist_dir = persist_dir
        Path(persist_dir).mkdir(parents=True, exist_ok=True)
        self._embedding_function = _HashingEmbeddingFunction()
        self._client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(anonymized_telemetry=False),
        )
        self._collections: dict[str, chromadb.Collection] = {}

    def _get_collection(self, name: str) -> chromadb.Collection:
        if name not in self._collections:
            self._collections[name] = self._client.get_or_create_collection(
                name=name,
                metadata={"hnsw:space": "cosine"},
                embedding_function=self._embedding_function,
            )
        return self._collections[name]

    def _sync_add(self, items: list[KnowledgeItem]) -> None:
        groups: dict[str, list[KnowledgeItem]] = {}
        for item in items:
            collection_name = self._SOURCE_TO_COLLECTION.get(item.source_type)
            if collection_name:
                groups.setdefault(collection_name, []).append(item)

        for collection_name, grouped_items in groups.items():
            collection = self._get_collection(collection_name)
            collection.upsert(
                ids=[item.chunk_id or str(uuid4()) for item in grouped_items],
                documents=[item.content for item in grouped_items],
                metadatas=[self._build_metadata(item) for item in grouped_items],
            )

    def _sync_delete(self, doc_id: str) -> None:
        for collection_name in self._SOURCE_TO_COLLECTION.values():
            collection = self._get_collection(collection_name)
            existing = collection.get(where={"doc_id": doc_id})
            if existing["ids"]:
                collection.delete(ids=existing["ids"])

    def _sync_retrieve(
        self,
        query: str,
        category: str | None,
        top_k: int,
    ) -> list[KnowledgeItem]:
        query_terms = extract_terms(query)
        results: list[KnowledgeItem] = []
        where = {"category": category} if category else None
        requested = max(top_k * 2, top_k)

        for collection_name in ("frameworks", "experiences"):
            collection = self._get_collection(collection_name)
            count = collection.count()
            if count <= 0:
                continue

            try:
                response = collection.query(
                    query_texts=[query],
                    n_results=min(requested, count),
                    where=where,
                    include=["documents", "metadatas", "distances"],
                )
            except Exception:
                continue

            documents = response.get("documents", [[]])[0]
            metadatas = response.get("metadatas", [[]])[0]
            distances = response.get("distances", [[]])[0]

            for document, metadata, distance in zip(documents, metadatas, distances):
                source_type = self._COLLECTION_TO_SOURCE[collection_name]
                score = self._score_hit(
                    query=query,
                    query_terms=query_terms,
                    document=document,
                    metadata=metadata or {},
                    distance=distance,
                    category=category,
                )
                results.append(
                    KnowledgeItem(
                        content=document,
                        source_type=source_type,
                        doc_id=(metadata or {}).get("doc_id", ""),
                        category=(metadata or {}).get("category") or None,
                        tags=self._split_csv((metadata or {}).get("tags")),
                        metadata={
                            "keywords": self._split_csv((metadata or {}).get("keywords")),
                            "source_path": (metadata or {}).get("source_path"),
                            "section_title": (metadata or {}).get("section_title"),
                            "section_path": (metadata or {}).get("section_path"),
                            "distance": distance,
                        },
                        chunk_id=(metadata or {}).get("chunk_id"),
                        score=score,
                        title=(metadata or {}).get("title") or (metadata or {}).get("section_title"),
                        retriever="vector_store",
                    )
                )

        results.sort(key=lambda item: (-item.score, item.source_type.priority, item.doc_id))
        return results[:top_k]

    async def add(self, items: list[KnowledgeItem]) -> None:
        await asyncio.to_thread(self._sync_add, items)

    async def delete_by_doc_id(self, doc_id: str) -> None:
        await asyncio.to_thread(self._sync_delete, doc_id)

    async def retrieve(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 5,
    ) -> list[KnowledgeItem]:
        return await asyncio.to_thread(self._sync_retrieve, query, category, top_k)

    @staticmethod
    def _build_metadata(item: KnowledgeItem) -> dict[str, str]:
        keywords = item.metadata.get("keywords", [])
        if isinstance(keywords, str):
            keywords_text = keywords
        else:
            keywords_text = ",".join(str(keyword).strip() for keyword in keywords if str(keyword).strip())

        return {
            "doc_id": item.doc_id,
            "chunk_id": item.chunk_id or "",
            "source_type": item.source_type.value,
            "category": item.category or "",
            "tags": ",".join(item.tags),
            "keywords": keywords_text,
            "title": item.title or "",
            "source_path": str(item.metadata.get("source_path", "")),
            "section_title": str(item.metadata.get("section_title", "")),
            "section_path": str(item.metadata.get("section_path", "")),
        }

    @classmethod
    def _score_hit(
        cls,
        *,
        query: str,
        query_terms: list[str],
        document: str,
        metadata: dict[str, object],
        distance: float | None,
        category: str | None,
    ) -> float:
        dense_score = 1 / (1 + max(distance or 0.0, 0.0))
        lexical_text = " ".join(
            filter(
                None,
                [
                    document,
                    str(metadata.get("title") or ""),
                    str(metadata.get("section_title") or ""),
                    str(metadata.get("keywords") or ""),
                    str(metadata.get("tags") or ""),
                ],
            )
        )
        lexical_terms = extract_terms(lexical_text)
        lexical_score = overlap_score(query_terms, lexical_terms)

        normalized_query = normalize_text(query)
        normalized_document = normalize_text(document)
        exact_bonus = 0.15 if normalized_query and normalized_query in normalized_document else 0.0
        keyword_bonus = 0.0
        for keyword in cls._split_csv(metadata.get("keywords")):
            if keyword and keyword in normalized_query:
                keyword_bonus = 0.1
                break
        category_bonus = 0.05 if category and metadata.get("category") == category else 0.0

        score = (dense_score * 0.65) + (lexical_score * 0.25) + exact_bonus + keyword_bonus + category_bonus
        return min(score, 1.0)

    @staticmethod
    def _split_csv(raw: object) -> list[str]:
        text = str(raw or "").strip()
        if not text:
            return []
        return [part.strip() for part in text.split(",") if part.strip()]
