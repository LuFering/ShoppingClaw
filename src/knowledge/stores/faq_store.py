from dataclasses import replace

from sqlalchemy import select

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import KnowledgeFaq

from ..core.base import RetrieverBase
from ..core.models import KnowledgeItem, SourceType
from ..core.text import extract_terms, normalize_text, overlap_score


class FAQStore(RetrieverBase):
    """FAQ retrieval with exact-first ranking and graceful DB fallback."""

    _SCAN_MULTIPLIER = 10
    _MIN_SCAN_ROWS = 20

    async def add(self, items: list[KnowledgeItem]) -> None:
        if not items or not self._is_available():
            return

        doc_ids = {item.doc_id for item in items}
        async with pg_manager.get_async_session_context() as session:
            old_rows = await session.execute(
                select(KnowledgeFaq).where(KnowledgeFaq.doc_id.in_(doc_ids))
            )
            for row in old_rows.scalars():
                await session.delete(row)

            for item in items:
                question = (
                    item.metadata.get("question")
                    or item.title
                    or item.doc_id
                )
                session.add(
                    KnowledgeFaq(
                        doc_id=item.doc_id,
                        question=str(question)[:500],
                        answer=item.content[:4000],
                        category=item.category,
                        tags=item.tags,
                        question_keywords=self._build_keywords(item, str(question)),
                    )
                )

    async def delete_by_doc_id(self, doc_id: str) -> None:
        if not self._is_available():
            return

        async with pg_manager.get_async_session_context() as session:
            rows = await session.execute(
                select(KnowledgeFaq).where(KnowledgeFaq.doc_id == doc_id)
            )
            for row in rows.scalars():
                await session.delete(row)

    async def retrieve(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 5,
    ) -> list[KnowledgeItem]:
        if not self._is_available():
            return []

        scan_limit = max(top_k * self._SCAN_MULTIPLIER, self._MIN_SCAN_ROWS)
        async with pg_manager.get_async_session_context() as session:
            stmt = select(KnowledgeFaq).where(KnowledgeFaq.is_active.is_(True))
            if category:
                stmt = stmt.where(KnowledgeFaq.category == category)
            stmt = stmt.order_by(KnowledgeFaq.updated_at.desc()).limit(scan_limit)
            rows = (await session.execute(stmt)).scalars().all()

        if not rows:
            return []

        scored_rows: list[tuple[float, KnowledgeFaq]] = []
        for row in rows:
            score = self._score_candidate(
                query=query,
                question=row.question,
                answer=row.answer,
                tags=row.tags or [],
                keywords=row.question_keywords or [],
            )
            if score > 0:
                scored_rows.append((score, row))

        if scored_rows:
            scored_rows.sort(key=lambda pair: pair[0], reverse=True)
            selected = scored_rows[:top_k]
        else:
            selected = [(0.05, row) for row in rows[:top_k]]

        return [
            KnowledgeItem(
                content=row.answer,
                source_type=SourceType.FAQ,
                doc_id=row.doc_id,
                category=row.category,
                tags=row.tags or [],
                metadata={"question": row.question, "question_keywords": row.question_keywords or []},
                score=score,
                title=row.question,
                retriever="faq_store",
            )
            for score, row in selected
        ]

    @staticmethod
    def _is_available() -> bool:
        return bool(getattr(pg_manager, "_initialized", False))

    @staticmethod
    def _build_keywords(item: KnowledgeItem, question: str) -> list[str]:
        values: list[str] = [question, *(item.tags or [])]
        raw_keywords = item.metadata.get("keywords", [])
        if isinstance(raw_keywords, str):
            values.extend(part.strip() for part in raw_keywords.split(",") if part.strip())
        else:
            values.extend(str(part).strip() for part in raw_keywords if str(part).strip())

        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            normalized = normalize_text(value)
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result

    @staticmethod
    def _score_candidate(
        *,
        query: str,
        question: str,
        answer: str,
        tags: list[str],
        keywords: list[str],
    ) -> float:
        normalized_query = normalize_text(query)
        normalized_question = normalize_text(question)
        normalized_answer = normalize_text(answer)
        query_terms = extract_terms(query)
        candidate_terms = extract_terms(" ".join([question, answer, *tags, *keywords]))

        score = 0.0
        if normalized_query and normalized_query == normalized_question:
            score += 0.75
        elif normalized_query and normalized_query in normalized_question:
            score += 0.55

        keyword_hits = sum(1 for keyword in keywords if keyword and keyword in normalized_query)
        if keyword_hits:
            score += min(0.2, keyword_hits * 0.08)

        if normalized_query and normalized_query in normalized_answer:
            score += 0.1

        score += 0.25 * overlap_score(query_terms, candidate_terms)
        return min(score, 1.0)
