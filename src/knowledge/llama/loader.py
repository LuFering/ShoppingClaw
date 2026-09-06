"""Markdown 文档加载 — 解析 frontmatter 并构造 LlamaIndex Document。

自建 loader 而非 MarkdownReader，以便精确控制 metadata 键
（source_type / doc_id / category / tags / keywords / title / question），
并校验 source_type 必须是合法枚举值。
"""

from __future__ import annotations

import logging
from pathlib import Path

import yaml
from llama_index.core import Document
from llama_index.core.schema import MetadataMode

from ..core.models import SourceType

logger = logging.getLogger(__name__)

# frontmatter 中可识别的 metadata 字段
_META_KEYS = (
    "source_type",
    "doc_id",
    "category",
    "tags",
    "keywords",
    "title",
    "question",
)

_FRONTMATTER_DELIM = "---"


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """从 Markdown 文本中解析 YAML frontmatter。

    Args:
        text: 原始 Markdown 文本（可能以 --- 开头）。

    Returns:
        (metadata, body) — metadata 为 frontmatter 解析出的 dict，body 为去除 frontmatter 的正文。
        无 frontmatter 时返回 ({}, text)。
    """
    stripped = text.lstrip("﻿")
    if not stripped.startswith(_FRONTMATTER_DELIM):
        return {}, stripped

    # 定位第二个 --- 分隔符
    lines = stripped.splitlines()
    end_idx = None
    for i in range(1, len(lines)):
        if lines[i].strip() == _FRONTMATTER_DELIM:
            end_idx = i
            break
    if end_idx is None:
        return {}, stripped

    header = "\n".join(lines[1:end_idx])
    body = "\n".join(lines[end_idx + 1:]).strip()
    try:
        meta = yaml.safe_load(header) or {}
    except yaml.YAMLError as exc:
        logger.warning("[KnowledgeLoader] frontmatter 解析失败: %s", exc)
        meta = {}
    if not isinstance(meta, dict):
        meta = {}
    return meta, body


def _normalize_list(value) -> list[str] | None:
    """把 frontmatter 中的字符串或列表归一为逗号分隔的字符串列表。"""
    if value is None:
        return None
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [part.strip() for part in value.split(",") if part.strip()]
    return None


def _split_csv(value) -> str:
    """列表 → 逗号分隔字符串（写入 node metadata 用，Chroma 不支持 list metadata 全场景）。"""
    if isinstance(value, str):
        return value
    return ",".join(str(item).strip() for item in (value or []) if str(item).strip())


def load_markdown_documents(docs_dir: str | Path) -> list[Document]:
    """递归加载目录下所有 Markdown，构造 Document 列表。

    Args:
        docs_dir: 知识文档根目录。

    Returns:
        合法的 Document 列表（source_type 非法或缺失的文档会被跳过并告警）。
    """
    root = Path(docs_dir)
    if not root.exists():
        logger.warning("[KnowledgeLoader] 知识目录不存在: %s", docs_dir)
        return []

    documents: list[Document] = []
    for md_file in sorted(root.rglob("*.md")):
        doc = _load_file(md_file)
        if doc is not None:
            documents.append(doc)
    return documents


def _load_file(md_file: Path) -> Document | None:
    try:
        text = md_file.read_text(encoding="utf-8")
    except Exception as exc:
        logger.warning("[KnowledgeLoader] 读取失败 %s: %s", md_file, exc)
        return None

    meta, body = parse_frontmatter(text)
    if not body.strip():
        logger.warning("[KnowledgeLoader] %s 正文为空，跳过", md_file)
        return None

    raw_source_type = str(meta.get("source_type", "")).strip().lower()
    if raw_source_type not in SourceType._value2member_map_:
        logger.warning(
            "[KnowledgeLoader] %s 的 source_type=%r 非法（应为 %s），跳过",
            md_file, raw_source_type, list(SourceType._value2member_map_.keys()),
        )
        return None

    doc_id = str(meta.get("doc_id") or md_file.stem).strip()
    tags = _normalize_list(meta.get("tags"))
    keywords = _normalize_list(meta.get("keywords"))

    # 过滤出合法字段；额外的 key 不写入，保持 metadata 干净
    node_meta = {
        "source_type": raw_source_type,
        "doc_id": doc_id,
        "category": str(meta.get("category") or "").strip(),
        "tags": _split_csv(tags),
        "keywords": _split_csv(keywords),
        "title": str(meta.get("title") or doc_id).strip(),
        "source_path": str(md_file).replace("\\", "/"),
    }
    if meta.get("question"):
        node_meta["question"] = str(meta.get("question")).strip()

    logger.info("[KnowledgeLoader] 加载 %s (type=%s, category=%s)", md_file.name, raw_source_type, node_meta["category"])
    return Document(
        text=body,
        metadata=node_meta,
        excluded_llm_metadata_keys=list(node_meta.keys()),
        excluded_embed_metadata_keys=list(node_meta.keys()),
        metadata_seperator="\n",
        metadata_template="{key}: {value}",
        text_template="{metadata_str}\n\n{content}",
    )


def _document_to_debug_str(doc: Document) -> str:
    """调试用：输出 Document 的 metadata 与正文预览。"""
    return doc.get_content(metadata_mode=MetadataMode.NONE)[:100]
