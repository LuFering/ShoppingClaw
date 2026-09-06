"""Embedding 模型工厂 — 支持 DashScope 官方包 与 OpenAI 兼容协议两种后端。

优先使用 DashScope 的 text-embedding-v3（中文检索效果好），
通过环境变量 KNOWLEDGE_EMBED_BACKEND=dashscope|openai 选择，
任一后端不可用/无 API Key 时回退到另一个，保证知识库可优雅降级。
"""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv

load_dotenv()  # 独立脚本 / lifespan 均能读到 .env 中的 DASHSCOPE_API_KEY

logger = logging.getLogger(__name__)

# DashScope OpenAI 兼容模式的 base_url（与 src/config/static/models.py 的 aliyun provider 一致）
_DASHSCOPE_OPENAI_BASE = "https://dashscope.aliyuncs.com/compatible-mode/v1"
_DEFAULT_MODEL = "text-embedding-v3"


def build_embed_model():
    """构建 LlamaIndex Embedding 模型实例。

    Returns:
        llama_index embedding 模型实例；若两个后端都不可用则返回 None
        （上层据此跳过索引构建，检索返回空）。
    """
    backend = os.getenv("KNOWLEDGE_EMBED_BACKEND", "dashscope").strip().lower()
    api_key = os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY") or ""

    if not api_key:
        logger.warning("[Embedding] 未配置 DASHSCOPE_API_KEY / OPENAI_API_KEY，知识库 embedding 不可用")
        return None

    if backend == "openai":
        model = _build_openai_compatible(api_key)
        if model is not None:
            return model
        logger.warning("[Embedding] OpenAI 兼容后端构建失败，回退 DashScope")
        return _build_dashscope(api_key)

    # 默认走 DashScope 官方包
    model = _build_dashscope(api_key)
    if model is not None:
        return model
    logger.warning("[Embedding] DashScope 后端构建失败，回退 OpenAI 兼容协议")
    return _build_openai_compatible(api_key)


def _build_dashscope(api_key: str):
    """DashScope 官方 embedding 包。"""
    try:
        from llama_index.embeddings.dashscope import DashScopeEmbedding

        return DashScopeEmbedding(
            model_name=_DEFAULT_MODEL,
            api_key=api_key,
            embed_batch_size=6,
        )
    except Exception as exc:  # 包缺失 / 参数不兼容
        logger.warning("[Embedding] DashScopeEmbedding 初始化失败: %s", exc)
        return None


def _build_openai_compatible(api_key: str):
    """OpenAI 兼容协议，指向 DashScope。"""
    try:
        from llama_index.embeddings.openai import OpenAIEmbedding

        return OpenAIEmbedding(
            model_name=_DEFAULT_MODEL,
            api_base=_DASHSCOPE_OPENAI_BASE,
            api_key=api_key,
            embed_batch_size=6,
        )
    except Exception as exc:
        logger.warning("[Embedding] OpenAIEmbedding(DashScope) 初始化失败: %s", exc)
        return None
