from dataclasses import dataclass, replace
from datetime import datetime

from ..core.base import RetrieverBase
from ..core.models import KnowledgeItem
from ..core.text import extract_terms, normalize_text, overlap_score


@dataclass(slots=True)
class _Rule:
    item: KnowledgeItem
    keywords: list[str]
    effective_date: datetime | None = None
    expire_date: datetime | None = None


class RuleEngine(RetrieverBase):
    """Exact-first rule matcher for policies and deterministic risk rules."""

    def __init__(self) -> None:
        self._store: dict[str, list[_Rule]] = {}

    async def add(self, items: list[KnowledgeItem]) -> None:
        for item in items:
            keywords = self._build_keywords(item)
            self._store.setdefault(item.doc_id, []).append(
                _Rule(
                    item=item,
                    keywords=keywords,
                    effective_date=self._parse_dt(item.metadata.get("effective_date")),
                    expire_date=self._parse_dt(item.metadata.get("expire_date")),
                )
            )

    async def delete_by_doc_id(self, doc_id: str) -> None:
        self._store.pop(doc_id, None)

    async def retrieve(
        self,
        query: str,
        category: str | None = None,
        top_k: int = 5,
    ) -> list[KnowledgeItem]:
        now = datetime.utcnow()
        normalized_query = normalize_text(query)
        query_terms = extract_terms(query)

        matched: list[KnowledgeItem] = []
        for rules in self._store.values():
            for rule in rules:
                if rule.expire_date and rule.expire_date < now:
                    continue
                if rule.effective_date and rule.effective_date > now:
                    continue
                if category and rule.item.category and rule.item.category != category:
                    continue

                keyword_hits = sum(
                    1 for keyword in rule.keywords if keyword and keyword in normalized_query
                )
                content_terms = extract_terms(
                    " ".join(
                        filter(
                            None,
                            [
                                rule.item.title or "",
                                rule.item.content,
                                " ".join(rule.item.tags),
                            ],
                        )
                    )
                )
                score = 0.0
                if keyword_hits:
                    score += min(0.7, 0.25 * keyword_hits)
                score += 0.25 * overlap_score(query_terms, content_terms)

                normalized_content = normalize_text(rule.item.content)
                if normalized_query and normalized_query in normalized_content:
                    score += 0.15
                if normalized_query and rule.item.title:
                    normalized_title = normalize_text(rule.item.title)
                    if normalized_title and normalized_title in normalized_query:
                        score += 0.1

                if score <= 0:
                    continue

                matched.append(
                    replace(
                        rule.item,
                        score=min(score, 1.0),
                        retriever="rule_engine",
                    )
                )

        matched.sort(key=lambda item: (-item.score, item.source_type.priority, item.doc_id))
        return matched[:top_k]

    @staticmethod
    def _parse_dt(value: object) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if isinstance(value, str) and value.strip():
            try:
                return datetime.fromisoformat(value.strip())
            except ValueError:
                return None
        return None

    @staticmethod
    def _build_keywords(item: KnowledgeItem) -> list[str]:
        raw_keywords = item.metadata.get("keywords", [])
        if isinstance(raw_keywords, str):
            candidates = [part.strip() for part in raw_keywords.split(",") if part.strip()]
        else:
            candidates = [str(part).strip() for part in raw_keywords if str(part).strip()]

        candidates.extend(item.tags)
        if item.title:
            candidates.append(item.title)

        result: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = normalize_text(candidate)
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result
