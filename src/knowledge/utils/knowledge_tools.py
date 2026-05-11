import logging

from src.agents.common.toolkits.registry import tool
from src.knowledge.manager import knowledge_manager

logger = logging.getLogger(__name__)


@tool(
    category="knowledge",
    tags=["知识库", "政策", "FAQ"],
    display_name="知识库检索",
    icon="📚",
)
async def query_knowledge(
    query: str,
    category: str | None = None,
) -> str:
    """Retrieve platform policy, decision framework and FAQ snippets."""

    result = await knowledge_manager.query_knowledge(query=query, category=category)
    if not result:
        return "知识库中未找到相关信息。"
    logger.info("[KnowledgeTool] query=%r -> %s chars", query, len(result))
    return result
