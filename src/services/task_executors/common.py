"""
任务执行器公共工具

所有执行器复用的 MCP 结果解析逻辑。
"""
import json
import logging

logger = logging.getLogger(__name__)


def parse_search_result(raw: str) -> list[dict]:
    """解析 MCP searchMaterial 返回的商品列表，兼容多种格式。

    MCP 返回值可能是：
    - JSON 字符串 '{"data": [...]}'
    - 已解析的 dict {"data": [...]}
    - 直接是 list [...]
    """
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        logger.warning(f"[TaskExecutor] 无法解析 MCP 返回结果: {str(raw)[:200]}")
        return []

    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("data", data.get("items", data.get("results", [])))
    return []
