"""会话持久化仓库 - PostgreSQL 事件溯源架构"""
import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from src.storage.postgres.models_business import Conversation


class ConversationRepository:
    """基于 PostgreSQL 的会话持久化仓库
    
    设计原则：
    1. 事件溯源：messages 字段存储完整的消息历史（JSONB 数组）
    2. 软删除：status 标记为 deleted，不物理删除数据
    3. 索引优化：user_id + updated_at 联合索引加速列表查询
    """

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create_conversation(
        self,
        user_id: str,
        agent_id: str,
        thread_id: str,
        title: str = "新对话",
        metadata: dict | None = None,
    ) -> Conversation:
        """创建新会话"""
        conversation = Conversation(
            thread_id=thread_id,
            user_id=user_id,
            agent_id=agent_id,
            title=title,
            status="active",
            is_pinned=False,
            conv_metadata=metadata or {},
            messages=[],
        )
        self.session.add(conversation)
        await self.session.commit()
        await self.session.refresh(conversation)
        return conversation

    async def get_by_thread_id(self, thread_id: str) -> Conversation | None:
        """根据 thread_id 获取会话"""
        stmt = select(Conversation).where(
            Conversation.thread_id == thread_id,
            Conversation.status != "deleted",
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_user(
        self,
        user_id: str,
        agent_id: str | None = None,
        status: str = "active",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Conversation]:
        """列出用户的会话（按更新时间倒序）"""
        stmt = (
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .where(Conversation.status == status)
        )

        if agent_id:
            stmt = stmt.where(Conversation.agent_id == agent_id)

        stmt = (
            stmt.order_by(Conversation.updated_at.desc())
            .limit(limit)
            .offset(offset)
        )

        result = await self.session.execute(stmt)
        return result.scalars().all()

    async def add_message(self, thread_id: str, message: dict) -> bool:
        """追加消息到会话历史（原子操作）"""
        # 使用 JSONB 数组追加操作
        stmt = (
            update(Conversation)
            .where(Conversation.thread_id == thread_id)
            .where(Conversation.status != "deleted")
            .values(
                messages=Conversation.messages.op("||")([message]),
                updated_at=datetime.utcnow(),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def add_messages_batch(self, thread_id: str, messages: list[dict]) -> bool:
        """批量追加消息（用于流式输出结束后一次性保存）"""
        if not messages:
            return True

        stmt = (
            update(Conversation)
            .where(Conversation.thread_id == thread_id)
            .where(Conversation.status != "deleted")
            .values(
                messages=Conversation.messages.op("||")(messages),
                updated_at=datetime.utcnow(),
            )
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def update_title(self, thread_id: str, title: str) -> bool:
        """更新会话标题"""
        stmt = (
            update(Conversation)
            .where(Conversation.thread_id == thread_id)
            .values(title=title, updated_at=datetime.utcnow())
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def update_metadata(self, thread_id: str, metadata: dict) -> bool:
        """更新会话元数据（合并而非覆盖）"""
        # 先获取现有元数据
        conv = await self.get_by_thread_id(thread_id)
        if not conv:
            return False

        merged_metadata = {**(conv.conv_metadata or {}), **metadata}

        stmt = (
            update(Conversation)
            .where(Conversation.thread_id == thread_id)
            .values(conv_metadata=merged_metadata, updated_at=datetime.utcnow())
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def pin_conversation(self, thread_id: str, is_pinned: bool) -> bool:
        """置顶/取消置顶会话"""
        stmt = (
            update(Conversation)
            .where(Conversation.thread_id == thread_id)
            .values(is_pinned=is_pinned, updated_at=datetime.utcnow())
        )
        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def delete_conversation(self, thread_id: str, soft_delete: bool = True) -> bool:
        """删除会话（默认软删除）"""
        if soft_delete:
            stmt = (
                update(Conversation)
                .where(Conversation.thread_id == thread_id)
                .values(status="deleted", updated_at=datetime.utcnow())
            )
        else:
            stmt = delete(Conversation).where(Conversation.thread_id == thread_id)

        result = await self.session.execute(stmt)
        await self.session.commit()
        return result.rowcount > 0

    async def get_messages(self, thread_id: str, limit: int | None = None) -> list[dict]:
        """获取会话消息历史"""
        conv = await self.get_by_thread_id(thread_id)
        if not conv:
            return []

        messages = conv.messages or []

        # 如果指定了 limit，返回最近 N 条消息
        if limit and len(messages) > limit:
            messages = messages[-limit:]

        return messages

    async def count_by_user(self, user_id: str, status: str = "active") -> int:
        """统计用户的会话数量"""
        from sqlalchemy import func

        stmt = (
            select(func.count())
            .select_from(Conversation)
            .where(Conversation.user_id == user_id)
            .where(Conversation.status == status)
        )
        result = await self.session.execute(stmt)
        return result.scalar() or 0

    async def update_conversation(
        self,
        thread_id: str,
        title: str | None = None,
        is_pinned: bool | None = None,
    ) -> Conversation | None:
        """更新会话标题和/或置顶状态，返回更新后的会话"""
        if title is not None:
            await self.update_title(thread_id, title)
        if is_pinned is not None:
            await self.pin_conversation(thread_id, is_pinned)
        await self.session.commit()
        return await self.get_by_thread_id(thread_id)

    async def get_attachments(self, conversation_id: int) -> list[dict]:
        """获取会话的附件列表"""
        conv = await self.session.get(Conversation, conversation_id)
        if not conv:
            return []
        attachments = conv.conv_metadata.get("attachments", []) if conv.conv_metadata else []
        return attachments if isinstance(attachments, list) else []

    async def remove_attachment(self, conversation_id: int, file_id: str) -> bool:
        """删除会话的指定附件"""
        conv = await self.session.get(Conversation, conversation_id)
        if not conv:
            return False
        metadata = dict(conv.conv_metadata or {})
        attachments = list(metadata.get("attachments", []))
        original_len = len(attachments)
        metadata["attachments"] = [a for a in attachments if a.get("file_id") != file_id]
        if len(metadata["attachments"]) == original_len:
            return False
        conv.conv_metadata = metadata
        conv.updated_at = datetime.utcnow()
        await self.session.commit()
        return True
