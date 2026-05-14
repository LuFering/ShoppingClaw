"""用户数据访问层 - Repository（PostgreSQL）"""

from datetime import UTC
from datetime import datetime as dt
from typing import Any

from sqlalchemy import func, select

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import User


def _utc_now():
    """获取当前 UTC 时间（naive）"""
    return dt.now(UTC).replace(tzinfo=None)


class UserRepository:
    """用户数据访问层"""

    async def get_by_id(self, user_id: int) -> User | None:
        """根据 ID 获取用户"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(User).where(User.id == user_id, User.is_deleted == 0))
            return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> User | None:
        """根据用户名获取用户"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(User).where(User.user_name == username, User.is_deleted == 0))
            return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: str) -> User | None:
        """根据登录ID获取用户"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(User).where(User.user_id == user_id, User.is_deleted == 0))
            return result.scalar_one_or_none()

    async def create(self, data: dict[str, Any]) -> User:
        """创建用户"""
        async with pg_manager.get_async_session_context() as session:
            user = User(**data)
            session.add(user)
            await session.commit()
            await session.refresh(user)
        return user

    async def update(self, user_id: int, data: dict[str, Any]) -> User | None:
        """更新用户"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(User).where(User.id == user_id, User.is_deleted == 0))
            user = result.scalar_one_or_none()
            if user is None:
                return None
            for key, value in data.items():
                if key != "id":
                    setattr(user, key, value)
            await session.commit()
            await session.refresh(user)
        return user

    async def exists_by_username(self, username: str) -> bool:
        """检查用户名是否存在"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(User.id).where(User.user_name == username, User.is_deleted == 0))
            return result.scalar_one_or_none() is not None
