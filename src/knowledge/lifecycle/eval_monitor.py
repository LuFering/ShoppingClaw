import logging

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import KnowledgeRetrievalLog

logger = logging.getLogger(__name__)


class EvalMonitor:
    """Persist retrieval telemetry when the business DB is available."""

    async def log(
        self,
        *,
        query: str,
        category: str | None,
        source_types: list[str] | None = None,
        result_count: int,
        latency_ms: int,
        is_hit: bool,
    ) -> None:
        if not getattr(pg_manager, "_initialized", False):
            logger.debug("[EvalMonitor] skip log because PostgreSQL is not initialized")
            return

        async with pg_manager.get_async_session_context() as session:
            session.add(
                KnowledgeRetrievalLog(
                    query=query[:500],
                    category=category,
                    source_types=source_types or [],
                    result_count=result_count,
                    latency_ms=latency_ms,
                    is_hit=is_hit,
                )
            )
