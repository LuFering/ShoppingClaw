from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.postgres.models_business import AgentConfig
from src.utils.datetime_utils import utc_now_naive

# 默认配置名称
DEFAULT_CONFIG_NAME = "初始配置"
class AgentConfigRepository:
    def __init__(self, db_session: AsyncSession):
        self.db = db_session

    async def get_by_id(self, config_id: int) -> AgentConfig | None:
        result = await self.db.execute(select(AgentConfig).where(AgentConfig.id == config_id))
        return result.scalar_one_or_none()
    async def get_default(self, *, agent_id: str) -> AgentConfig | None:
        result = await self.db.execute(
            select(AgentConfig).where(
                AgentConfig.agent_id == agent_id,
                AgentConfig.is_default.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def get_or_create_default(
            self,
            *,
            agent_id: str,
            created_by: str | None = None,
    ) -> AgentConfig:
        existing = await self.get_default( agent_id=agent_id)
        if existing:
            return existing


        config = AgentConfig(
            agent_id=agent_id,
            name=DEFAULT_CONFIG_NAME,
            description=None,
            icon=None,
            pics=[],
            examples=[],
            config_json={},
            is_default=True,
            created_by=created_by,
            updated_by=created_by,
            created_at=utc_now_naive(),
            updated_at=utc_now_naive(),
        )
        self.db.add(config)
        await self.db.commit()
        await self.db.refresh(config)
        return config
