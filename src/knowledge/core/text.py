import re
from collections.abc import Iterable


_NON_WORD_RE = re.compile(r"[^0-9a-zA-Z\u4e00-\u9fff]+", re.UNICODE)
_LATIN_TERM_RE = re.compile(r"[a-z0-9]+")
_CJK_TERM_RE = re.compile(r"[\u4e00-\u9fff]+")


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    lowered = text.casefold()
    cleaned = _NON_WORD_RE.sub(" ", lowered)
    return " ".join(cleaned.split())


def extract_terms(text: str | None) -> list[str]:
    normalized = normalize_text(text)
    if not normalized:
        return []

    terms: list[str] = []
    seen: set[str] = set()

    for term in _LATIN_TERM_RE.findall(normalized):
        if term not in seen:
            seen.add(term)
            terms.append(term)

    for segment in _CJK_TERM_RE.findall(normalized):
        if segment not in seen:
            seen.add(segment)
            terms.append(segment)
        if len(segment) <= 3:
            continue
        for idx in range(len(segment) - 1):
            bigram = segment[idx : idx + 2]
            if bigram not in seen:
                seen.add(bigram)
                terms.append(bigram)

    if not terms and normalized not in seen:
        terms.append(normalized)
    return terms


def overlap_score(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = {term for term in left if term}
    right_set = {term for term in right if term}
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set)
