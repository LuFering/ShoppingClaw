"""MCP 服务器数据访问层 - Repository"""
from __future__ import annotations

from typing import Any

from sqlalchemy import select

from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import MCPServer


class MCPServerRepository:
    """MCP 服务器数据访问层"""

    async def get_by_name(self, name: str) -> MCPServer | None:
        """根据名称获取 MCP 服务器"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(MCPServer).where(MCPServer.name == name))
            return result.scalar_one_or_none()

    async def list(self) -> list[MCPServer]:
        """获取所有 MCP 服务器"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(MCPServer))
            return list(result.scalars().all())

    async def list_enabled(self) -> list[MCPServer]:
        """获取所有启用的 MCP 服务器"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(MCPServer).where(MCPServer.enabled.is_(True)))
            return list(result.scalars().all())

    async def create(self, data: dict[str, Any]) -> MCPServer:
        """创建 MCP 服务器"""
        async with pg_manager.get_async_session_context() as session:
            server = MCPServer(**data)
            session.add(server)
            await session.flush()
            await session.refresh(server)
        return server

    async def update(self, name: str, data: dict[str, Any]) -> MCPServer | None:
        """更新 MCP 服务器"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(MCPServer).where(MCPServer.name == name))
            server = result.scalar_one_or_none()
            if server is None:
                return None
            for key, value in data.items():
                if key != "name":
                    setattr(server, key, value)
        return server

    async def delete(self, name: str) -> bool:
        """删除 MCP 服务器"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(MCPServer).where(MCPServer.name == name))
            server = result.scalar_one_or_none()
            if server is None:
                return False
            await session.delete(server)
        return True

    async def upsert(self, data: dict[str, Any]) -> MCPServer:
        """插入或更新 MCP 服务器"""
        name = data.get("name")
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(MCPServer).where(MCPServer.name == name))
            existing = result.scalar_one_or_none()
            if existing is None:
                server = MCPServer(**data)
                session.add(server)
            else:
                for key, value in data.items():
                    if key != "name":
                        setattr(existing, key, value)
                server = existing
            await session.flush()
            await session.refresh(server)
        return server

    async def exists_by_name(self, name: str) -> bool:
        """检查 MCP 服务器是否存在"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(MCPServer.id).where(MCPServer.name == name))
            return result.scalar_one_or_none() is not None

    # ── 按 id 操作（2026-09-22 新增：前端按 id 增删改）──

    async def get_by_id(self, server_id: str) -> MCPServer | None:
        """根据 id 获取 MCP 服务器"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(MCPServer).where(MCPServer.id == server_id)
            )
            return result.scalar_one_or_none()

    async def update_by_id(self, server_id: str, data: dict[str, Any]) -> MCPServer | None:
        """按 id 更新（不改 id / name）"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(MCPServer).where(MCPServer.id == server_id)
            )
            server = result.scalar_one_or_none()
            if server is None:
                return None
            for key, value in data.items():
                if key in ("id", "name"):
                    continue
                setattr(server, key, value)
            await session.flush()
            await session.refresh(server)
        return server

    async def delete_by_id(self, server_id: str) -> bool:
        """按 id 删除"""
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(
                select(MCPServer).where(MCPServer.id == server_id)
            )
            server = result.scalar_one_or_none()
            if server is None:
                return False
            await session.delete(server)
        return True
