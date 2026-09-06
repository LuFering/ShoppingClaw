import logging
import re
import uuid
from pathlib import Path

from ..core.models import KnowledgeItem, SourceType

logger = logging.getLogger(__name__)

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*", re.DOTALL)
_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")


class MarkdownIndexer:
    """Index markdown files into stable, metadata-rich chunks."""

    def __init__(
        self,
        *,
        max_chunk_chars: int = 900,
        min_chunk_chars: int = 180,
        chunk_overlap_chars: int = 120,
    ) -> None:
        self._max_chunk_chars = max_chunk_chars
        self._min_chunk_chars = min_chunk_chars
        self._chunk_overlap_chars = chunk_overlap_chars

    def index_file(self, path: str | Path) -> list[KnowledgeItem]:
        file_path = Path(path)
        text = file_path.read_text(encoding="utf-8")
        meta = self._parse_frontmatter(text)
        body = self._strip_frontmatter(text)
        if not body:
            return []

        source_type = SourceType(meta.get("source_type", SourceType.EXPERIENCE.value))
        doc_id = meta.get("doc_id") or file_path.stem
        category = meta.get("category")
        tags = self._parse_csv(meta.get("tags"))
        keywords = self._parse_csv(meta.get("keywords"))

        items: list[KnowledgeItem] = []
        sections = self._split_sections(body)
        for section_index, section in enumerate(sections):
            chunks = self._chunk_text(section["body"])
            if not chunks:
                continue

            for chunk_index, chunk in enumerate(chunks):
                title = section["title"]
                content = self._compose_content(title, chunk)
                item_meta = {
                    "keywords": keywords,
                    "source_path": str(file_path),
                    "section_title": title,
                    "section_path": section["path"],
                }
                if source_type is SourceType.FAQ:
                    item_meta["question"] = title or meta.get("question") or doc_id

                stable_key = f"{doc_id}:{section_index}:{chunk_index}:{title}:{chunk[:80]}"
                items.append(
                    KnowledgeItem(
                        content=content,
                        source_type=source_type,
                        doc_id=doc_id,
                        category=category,
                        tags=tags,
                        metadata=item_meta,
                        chunk_id=str(uuid.uuid5(uuid.NAMESPACE_URL, stable_key)),
                        title=title,
                    )
                )

        if not items:
            fallback_key = f"{doc_id}:0:{body[:120]}"
            items.append(
                KnowledgeItem(
                    content=body.strip(),
                    source_type=source_type,
                    doc_id=doc_id,
                    category=category,
                    tags=tags,
                    metadata={
                        "keywords": keywords,
                        "source_path": str(file_path),
                        "question": meta.get("question") or doc_id if source_type is SourceType.FAQ else None,
                    },
                    chunk_id=str(uuid.uuid5(uuid.NAMESPACE_URL, fallback_key)),
                    title=meta.get("title") or file_path.stem,
                )
            )

        return items

    def index_directory(self, dir_path: str | Path) -> list[KnowledgeItem]:
        items: list[KnowledgeItem] = []
        for md_file in sorted(Path(dir_path).rglob("*.md")):
            try:
                items.extend(self.index_file(md_file))
            except Exception as exc:
                logger.warning("[KnowledgeIndexer] skip %s: %s", md_file, exc)
        return items

    @staticmethod
    def _parse_frontmatter(text: str) -> dict[str, str]:
        match = _FRONTMATTER_RE.match(text)
        if not match:
            return {}

        meta: dict[str, str] = {}
        for raw_line in match.group(1).splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or ":" not in line:
                continue
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
        return meta

    @staticmethod
    def _strip_frontmatter(text: str) -> str:
        return _FRONTMATTER_RE.sub("", text, count=1).strip()

    @staticmethod
    def _parse_csv(raw: str | None) -> list[str]:
        if not raw:
            return []
        return [part.strip() for part in raw.split(",") if part.strip()]

    def _split_sections(self, body: str) -> list[dict[str, str]]:
        sections: list[dict[str, str]] = []
        current_title = ""
        current_path = ""
        current_lines: list[str] = []
        heading_stack: list[str] = []

        def flush_section() -> None:
            content = "\n".join(current_lines).strip()
            if not content:
                return
            sections.append(
                {
                    "title": current_title,
                    "path": current_path,
                    "body": content,
                }
            )

        for line in body.splitlines():
            match = _HEADING_RE.match(line.strip())
            if not match:
                current_lines.append(line)
                continue

            flush_section()
            current_lines = []

            level = len(match.group(1))
            heading = match.group(2).strip()
            heading_stack = heading_stack[: level - 1]
            heading_stack.append(heading)
            current_title = heading
            current_path = " > ".join(heading_stack)

        flush_section()

        if sections:
            return sections
        return [{"title": "", "path": "", "body": body.strip()}]

    def _chunk_text(self, text: str) -> list[str]:
        text = text.strip()
        if not text:
            return []
        if len(text) <= self._max_chunk_chars:
            return [text]

        paragraphs = [part.strip() for part in re.split(r"\n{2,}", text) if part.strip()]
        chunks: list[str] = []
        current = ""

        for paragraph in paragraphs or [text]:
            candidate = f"{current}\n\n{paragraph}".strip() if current else paragraph
            if current and len(candidate) > self._max_chunk_chars:
                chunks.append(current)
                overlap = current[-self._chunk_overlap_chars :].strip()
                current = f"{overlap}\n\n{paragraph}".strip() if overlap else paragraph
                if len(current) > self._max_chunk_chars:
                    chunks.extend(self._force_split(current))
                    current = ""
            else:
                current = candidate

        if current:
            if chunks and len(current) < self._min_chunk_chars:
                chunks[-1] = f"{chunks[-1]}\n\n{current}".strip()
            else:
                chunks.append(current)
        return chunks

    def _force_split(self, text: str) -> list[str]:
        parts: list[str] = []
        start = 0
        step = max(1, self._max_chunk_chars - self._chunk_overlap_chars)
        while start < len(text):
            end = min(len(text), start + self._max_chunk_chars)
            parts.append(text[start:end].strip())
            if end == len(text):
                break
            start += step
        return [part for part in parts if part]

    @staticmethod
    def _compose_content(title: str, chunk: str) -> str:
        title = title.strip()
        chunk = chunk.strip()
        if not title:
            return chunk
        if chunk.startswith(title):
            return chunk
        return f"{title}\n{chunk}"
