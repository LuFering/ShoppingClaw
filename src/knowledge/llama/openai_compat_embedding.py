"""自建 OpenAI 兼容 embedding —— 直接调 HTTP 端点，不依赖额外包。

背景（2026-09-22）：
  · DashScope 账号**欠费**，embedding 调用被拒（code=Arrearage）
  · 项目只装了 `llama-index-embeddings-dashscope`，**没装**
    `llama-index-embeddings-openai` —— 所以原 `_build_openai_compatible`
    一直是死代码（ImportError 被 except 吞掉）
  · `llama_index.core.embeddings` 里也没有 OpenAIEmbedding（那在独立包里）

方案：继承 `BaseEmbedding` 自己实现，直接 POST 到 OpenAI 兼容的
`/embeddings` 端点（实测 OpenRouter 可用）。不装新包、不改 pyproject、
不重建容器。

⚠️ 用 requests 同步调用 —— 调用方（KnowledgeManager）已用
   `asyncio.to_thread` 包裹，不会阻塞事件循环。
"""
from __future__ import annotations

import logging
import os
from typing import Any, List

import requests
from llama_index.core.embeddings import BaseEmbedding

logger = logging.getLogger(__name__)


class OpenAICompatibleEmbedding(BaseEmbedding):
    """OpenAI 兼容协议的 embedding（自实现，零额外依赖）。

    Args:
        model_name: 模型名，如 openai/text-embedding-3-small
        api_base: 形如 https://openrouter.ai/api/v1（**不要**带 /embeddings）
        api_key: 对应服务的 key
        timeout: 单次请求超时（秒）
        embed_batch_size: 批量大小
    """

    def __init__(
        self,
        model_name: str,
        api_base: str,
        api_key: str,
        timeout: int = 30,
        embed_batch_size: int = 6,
        **kwargs: Any,
    ) -> None:
        super().__init__(embed_batch_size=embed_batch_size, **kwargs)
        self._model_name = model_name
        self._api_base = (api_base or "").rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    # ── 内部：一次 HTTP 调用拿多条向量 ──

    def _embed(self, texts: List[str]) -> List[List[float]]:
        """调 /embeddings，返回与输入等长的向量列表。

        失败时抛异常（由调用方决定降级策略）—— 静默返回空向量会让
        上层把「全零向量」当成有效结果写进向量库，污染检索。
        """
        if not texts:
            return []
        url = f"{self._api_base}/embeddings"
        try:
            resp = requests.post(
                url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={"model": self._model_name, "input": texts},
                timeout=self._timeout,
            )
        except requests.RequestException as exc:
            raise RuntimeError(f"embedding 请求失败: {exc}") from exc

        if resp.status_code != 200:
            raise RuntimeError(
                f"embedding 返回 {resp.status_code}: {resp.text[:200]}"
            )

        payload = resp.json()
        data = payload.get("data") or []
        if len(data) != len(texts):
            raise RuntimeError(
                f"embedding 返回条数不符: 期望 {len(texts)}，实得 {len(data)}"
            )

        # 按 index 排序（协议不保证顺序）
        ordered = sorted(data, key=lambda d: d.get("index", 0))
        out = [d.get("embedding") or [] for d in ordered]
        if any(not v for v in out):
            raise RuntimeError("embedding 返回了空向量")
        return out

    # ── BaseEmbedding 要求的四个方法 ──

    def _get_query_embedding(self, query: str) -> List[float]:
        return self._embed([query])[0]

    def _get_text_embedding(self, text: str) -> List[float]:
        return self._embed([text])[0]

    async def _aget_query_embedding(self, query: str) -> List[float]:
        # 同步实现即可：调用方已用 to_thread 包裹
        return self._get_query_embedding(query)

    async def _aget_text_embedding(self, text: str) -> List[float]:
        return self._get_text_embedding(text)

    def _get_text_embeddings(self, texts: List[str]) -> List[List[float]]:
        """批量（覆盖基类逐条实现，减少 HTTP 往返）。"""
        return self._embed(texts)


def build_openrouter_embedding(api_key: str | None = None):
    """构造指向 OpenRouter 的 embedding 实例。

    Returns:
        实例；key 缺失时返回 None（上层跳过索引构建）
    """
    key = api_key or os.getenv("OPENROUTER_API_KEY") or ""
    if not key:
        logger.warning("[Embedding] 未配置 OPENROUTER_API_KEY")
        return None
    base = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1")
    model = os.getenv("KNOWLEDGE_EMBED_MODEL", "openai/text-embedding-3-small")
    try:
        return OpenAICompatibleEmbedding(
            model_name=model,
            api_base=base,
            api_key=key,
        )
    except Exception as exc:
        logger.warning("[Embedding] OpenRouter embedding 构造失败: %s", exc)
        return None
