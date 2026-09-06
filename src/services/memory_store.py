"""进程内内存存储 — 数据库不可用时的降级方案"""

import uuid
from datetime import datetime
from typing import Optional


class MemoryStore:
    """进程内内存存储，用于替代数据库不可用时的线程/消息存储"""

    def __init__(self):
        self._threads: dict[str, dict] = {}
        self._messages: dict[str, list[dict]] = {}

    def create_thread(self, agent_id: str, title: str, user_id: str) -> dict:
        thread_id = str(uuid.uuid4())
        now = datetime.now().isoformat()
        thread = {
            "id": thread_id,
            "user_id": user_id,
            "agent_id": agent_id,
            "title": title or "新的对话",
            "is_pinned": False,
            "created_at": now,
            "updated_at": now,
        }
        self._threads[thread_id] = thread
        self._messages[thread_id] = []
        return thread

    def list_threads(
        self,
        user_id: Optional[str] = None,
        agent_id: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list:
        threads = list(self._threads.values())
        if user_id:
            threads = [t for t in threads if t["user_id"] == user_id]
        if agent_id:
            threads = [t for t in threads if t["agent_id"] == agent_id]
        threads.sort(key=lambda t: t["updated_at"], reverse=True)
        return threads[offset : offset + limit]

    def get_thread(self, thread_id: str) -> dict | None:
        return self._threads.get(thread_id)

    def delete_thread(self, thread_id: str) -> bool:
        self._messages.pop(thread_id, None)
        return self._threads.pop(thread_id, None) is not None

    def update_thread(
        self,
        thread_id: str,
        title: str | None = None,
        is_pinned: bool | None = None,
    ) -> dict | None:
        thread = self._threads.get(thread_id)
        if not thread:
            return None
        if title is not None:
            thread["title"] = title
        if is_pinned is not None:
            thread["is_pinned"] = is_pinned
        thread["updated_at"] = datetime.now().isoformat()
        return thread

    def add_message(self, thread_id: str, message: dict) -> None:
        if thread_id not in self._messages:
            self._messages[thread_id] = []
        self._messages[thread_id].append(message)

    def get_messages(self, thread_id: str) -> list:
        return self._messages.get(thread_id, [])


memory_store = MemoryStore()
