"""Redis 持久化存储 — 替代进程内 MemoryStore

使用 Redis 数据结构：
- 线程元数据: Hash (thread:{thread_id})
- 线程列表: Sorted Set (user:{user_id}:threads)
- 消息列表: List (thread:{thread_id}:messages)
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from src.services.redis_cache import get_redis_cache


class RedisStore:
    """Redis 支持的线程/消息存储，替代 MemoryStore"""

    _THREAD_KEY = "thread:{}"            # Hash: thread metadata
    _USER_THREADS_KEY = "user:{}:threads"  # Sorted Set: thread list
    _MESSAGES_KEY = "thread:{}:messages"   # List: messages

    def __init__(self):
        self._cache = get_redis_cache()

    async def _ensure_connected(self):
        if not self._cache._connected:
            await self._cache.connect()
        return self._cache._redis

    # ── Thread CRUD ──

    async def create_thread(self, agent_id: str, title: str, user_id: str) -> dict:
        r = await self._ensure_connected()
        thread_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).isoformat()
        thread = {
            "id": thread_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "title": title or "新的对话",
            "is_pinned": "false",
            "created_at": now,
            "updated_at": now,
        }
        # Hash 存储线程详情
        await r.hset(self._THREAD_KEY.format(thread_id), mapping=thread)
        # Sorted Set 按更新时间排序
        await r.zadd(self._USER_THREADS_KEY.format(user_id), {thread_id: datetime.now(timezone.utc).timestamp()})
        # 确保 thread_id 可重建为 Python bool
        thread["is_pinned"] = False
        return thread

    async def list_threads(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list:
        r = await self._ensure_connected()
        if not user_id:
            # 无 user_id 时扫描所有 thread:* hash（效率较低，仅降级用）
            result = []
            async for key in r.scan_iter(match=self._THREAD_KEY.format("*")):
                data = await r.hgetall(key)
                if data:
                    result.append(self._parse_thread(data))
                    if len(result) >= offset + limit:
                        break
            return result[offset:offset + limit]

        # 从 Sorted Set 获取线程 ID 列表（按更新时间倒序）
        thread_ids = await r.zrevrange(
            self._USER_THREADS_KEY.format(user_id),
            offset, offset + limit - 1,
        )
        threads = []
        for tid in thread_ids:
            data = await r.hgetall(self._THREAD_KEY.format(tid))
            if data:
                thread = self._parse_thread(data)
                if agent_id is None or thread["agent_id"] == agent_id:
                    threads.append(thread)
        return threads

    async def get_thread(self, thread_id: str) -> dict | None:
        r = await self._ensure_connected()
        data = await r.hgetall(self._THREAD_KEY.format(thread_id))
        return self._parse_thread(data) if data else None

    async def delete_thread(self, thread_id: str) -> bool:
        r = await self._ensure_connected()
        thread = await r.hgetall(self._THREAD_KEY.format(thread_id))
        if not thread:
            return False
        user_id = thread.get("user_id", "")
        await r.delete(self._THREAD_KEY.format(thread_id))
        await r.delete(self._MESSAGES_KEY.format(thread_id))
        if user_id:
            await r.zrem(self._USER_THREADS_KEY.format(user_id), thread_id)
        return True

    async def update_thread(
        self,
        thread_id: str,
        title: str | None = None,
        is_pinned: bool | None = None,
    ) -> dict | None:
        r = await self._ensure_connected()
        key = self._THREAD_KEY.format(thread_id)
        exists = await r.exists(key)
        if not exists:
            return None
        updates = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if title is not None:
            updates["title"] = title
        if is_pinned is not None:
            updates["is_pinned"] = str(is_pinned).lower()
        await r.hset(key, mapping=updates)
        # 更新用户线程列表中的排序分数
        thread = await r.hgetall(key)
        if thread and thread.get("user_id"):
            await r.zadd(
                self._USER_THREADS_KEY.format(thread["user_id"]),
                {thread_id: datetime.now(timezone.utc).timestamp()},
            )
        return self._parse_thread(thread) if thread else None

    # ── Message CRUD ──

    async def add_message(self, thread_id: str, message: dict) -> None:
        r = await self._ensure_connected()
        # 确保 timestamp 存在
        if "timestamp" not in message:
            message["timestamp"] = datetime.now(timezone.utc).isoformat()
        await r.rpush(
            self._MESSAGES_KEY.format(thread_id),
            json.dumps(message, ensure_ascii=False),
        )
        # 更新线程的 updated_at
        await r.hset(
            self._THREAD_KEY.format(thread_id),
            "updated_at",
            datetime.now(timezone.utc).isoformat(),
        )

    async def get_messages(self, thread_id: str) -> list:
        r = await self._ensure_connected()
        raw = await r.lrange(self._MESSAGES_KEY.format(thread_id), 0, -1)
        messages = []
        for item in raw:
            try:
                msg = json.loads(item)
                # 还原 is_pinned 为 bool（存储时是字符串）
                if isinstance(msg, dict):
                    messages.append(msg)
                else:
                    messages.append({"content": str(msg)})
            except json.JSONDecodeError:
                messages.append({"content": str(item)})
        return messages

    # ── Helpers ──

    @staticmethod
    def _parse_thread(data: dict) -> dict:
        """将 Redis Hash 数据转为标准 thread 格式"""
        if not data:
            return {}
        result = dict(data)
        # 还原 is_pinned 为 bool
        if "is_pinned" in result:
            result["is_pinned"] = result["is_pinned"] in ("true", "True", "1")
        return result


# 全局单例
redis_store = RedisStore()


async def get_message_store():
    """获取消息存储：Redis 优先，不可用时降级到内存

    返回 (store, is_redis) 元组
    - store: 实现了 add_message/get_messages 接口的对象
    - is_redis: 是否使用了 Redis
    """
    from src.services.memory_store import memory_store
    try:
        await redis_store._ensure_connected()
        return redis_store, True
    except Exception:
        return memory_store, False


class MessageStoreBridge:
    """统一的消息存储桥接 — Redis + 内存双写 / 降级

    用法：
        store = MessageStoreBridge()
        await store.add_message(thread_id, msg)      # 双写到 Redis + 内存
        msgs = await store.get_messages(thread_id)    # 优先 Redis
        threads = await store.list_threads(user_id)   # 优先 Redis
    """

    async def _call(self, name: str, *args, **kwargs):
        """Redis 优先执行；任何命令级异常降级到 memory_store，绝不向调用方抛出

        Redis 仅是加速/影子层，PostgreSQL 才是消息主存储。Redis 故障（宕机、
        跨事件循环等）不得阻断线程/消息的创建与保存流程。
        """
        from src.services.memory_store import memory_store
        try:
            await redis_store._ensure_connected()
        except Exception as e:
            logging.warning(f"[Store] Redis 不可用（{e}），{name} 降级 memory_store")
            return getattr(memory_store, name)(*args, **kwargs)
        try:
            return await getattr(redis_store, name)(*args, **kwargs)
        except Exception as e:
            logging.warning(f"[Store] Redis {name} 失败（{e}），降级 memory_store")
            return getattr(memory_store, name)(*args, **kwargs)

    async def create_thread(self, *args, **kwargs):
        return await self._call("create_thread", *args, **kwargs)

    async def list_threads(self, *args, **kwargs):
        return await self._call("list_threads", *args, **kwargs)

    async def get_thread(self, *args, **kwargs):
        return await self._call("get_thread", *args, **kwargs)

    async def delete_thread(self, *args, **kwargs):
        return await self._call("delete_thread", *args, **kwargs)

    async def update_thread(self, *args, **kwargs):
        return await self._call("update_thread", *args, **kwargs)

    async def add_message(self, *args, **kwargs):
        return await self._call("add_message", *args, **kwargs)

    async def get_messages(self, *args, **kwargs):
        return await self._call("get_messages", *args, **kwargs)
