"""用户记忆服务 - 双层记忆架构

参考 ScienceClaw 的设计，实现双层记忆系统：
1. 全局记忆（AGENTS.md）：跨会话持久化的用户偏好、习惯、背景信息
2. 会话上下文（CONTEXT.md）：当前会话的临时上下文，会话结束后丢弃

核心优势：
- 全局记忆让 Agent "记住"用户的长期偏好
- 会话上下文保持当前对话的连贯性
- 文件存储简单可靠，易于调试和备份
"""
import logging
from pathlib import Path
from typing import Optional


class UserMemoryService:
    """用户全局记忆 + 会话上下文 双层记忆服务
    
    存储结构：
    saves/memory/
    ├── {user_id}/
    │   └── AGENTS.md          # 全局记忆
    └── sessions/
        └── {thread_id}/
            └── CONTEXT.md     # 会话上下文
    """
    
    def __init__(self, base_dir: str = "saves/memory"):
        """初始化记忆服务
        
        Args:
            base_dir: 基础存储目录
        """
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        
        # 创建子目录
        (self.base_dir / "sessions").mkdir(exist_ok=True)
    
    async def get_global_memory(self, user_id: str) -> str:
        """获取用户全局记忆 (AGENTS.md)
        
        Args:
            user_id: 用户 ID
            
        Returns:
            全局记忆内容（最多 4000 字符），如果不存在则返回空字符串
        """
        memory_file = self.base_dir / user_id / "AGENTS.md"
        
        if memory_file.exists():
            try:
                content = memory_file.read_text(encoding="utf-8")
                # 截断到 4000 字符，避免占用过多 context
                truncated = content[:4000]
                
                if len(content) > 4000:
                    logging.debug(
                        f"[UserMemory] Global memory truncated: "
                        f"{len(content)} -> 4000 chars"
                    )
                
                return truncated
                
            except Exception as e:
                logging.error(f"[UserMemory] Failed to read global memory: {e}")
                return ""
        
        return ""
    
    async def update_global_memory(self, user_id: str, content: str):
        """更新用户全局记忆
        
        Args:
            user_id: 用户 ID
            content: 新的记忆内容
        """
        memory_file = self.base_dir / user_id / "AGENTS.md"
        memory_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            memory_file.write_text(content, encoding="utf-8")
            logging.info(
                f"[UserMemory] Global memory updated for user {user_id} "
                f"({len(content)} chars)"
            )
        except Exception as e:
            logging.error(f"[UserMemory] Failed to write global memory: {e}")
            raise
    
    async def append_to_global_memory(self, user_id: str, new_content: str):
        """追加到全局记忆（而非覆盖）
        
        Args:
            user_id: 用户 ID
            new_content: 要追加的内容
        """
        existing = await self.get_global_memory(user_id)
        
        if existing:
            combined = f"{existing}\n\n{new_content}"
        else:
            combined = new_content
        
        await self.update_global_memory(user_id, combined)
    
    async def get_session_context(self, thread_id: str) -> str:
        """获取会话上下文 (CONTEXT.md)
        
        Args:
            thread_id: 会话 ID
            
        Returns:
            会话上下文内容，如果不存在则返回空字符串
        """
        context_file = self.base_dir / "sessions" / thread_id / "CONTEXT.md"
        
        if context_file.exists():
            try:
                return context_file.read_text(encoding="utf-8")
            except Exception as e:
                logging.error(f"[UserMemory] Failed to read session context: {e}")
                return ""
        
        return ""
    
    async def update_session_context(self, thread_id: str, content: str):
        """更新会话上下文
        
        Args:
            thread_id: 会话 ID
            content: 新的上下文内容
        """
        context_file = self.base_dir / "sessions" / thread_id / "CONTEXT.md"
        context_file.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            context_file.write_text(content, encoding="utf-8")
            logging.debug(
                f"[UserMemory] Session context updated for thread {thread_id} "
                f"({len(content)} chars)"
            )
        except Exception as e:
            logging.error(f"[UserMemory] Failed to write session context: {e}")
            raise
    
    async def clear_session_context(self, thread_id: str):
        """清除会话上下文（会话结束时调用）
        
        Args:
            thread_id: 会话 ID
        """
        context_file = self.base_dir / "sessions" / thread_id / "CONTEXT.md"
        
        if context_file.exists():
            try:
                context_file.unlink()
                logging.info(f"[UserMemory] Session context cleared for thread {thread_id}")
            except Exception as e:
                logging.error(f"[UserMemory] Failed to clear session context: {e}")
    
    async def build_system_prompt_context(
        self,
        user_id: str,
        thread_id: Optional[str] = None,
    ) -> str:
        """构建系统提示词的上下文部分
        
        将全局记忆和会话上下文合并为一段文本，插入到 system prompt 中。
        
        Args:
            user_id: 用户 ID
            thread_id: 会话 ID（可选）
            
        Returns:
            格式化的上下文字符串
        """
        parts = []
        
        # 1. 全局记忆
        global_memory = await self.get_global_memory(user_id)
        if global_memory:
            parts.append("## 用户全局记忆\n")
            parts.append(global_memory)
            parts.append("")
        
        # 2. 会话上下文
        if thread_id:
            session_context = await self.get_session_context(thread_id)
            if session_context:
                parts.append("## 当前会话上下文\n")
                parts.append(session_context)
                parts.append("")
        
        if not parts:
            return ""
        
        return "\n".join(parts)
    
    async def extract_and_save_preferences(
        self,
        user_id: str,
        conversation_summary: str,
    ):
        """从对话摘要中提取用户偏好并保存到全局记忆
        
        这是一个高级功能，可以结合 LLM 自动提取用户偏好。
        
        Args:
            user_id: 用户 ID
            conversation_summary: 对话摘要
        """
        # TODO: 使用 LLM 提取关键偏好信息
        # 示例实现：直接追加摘要
        await self.append_to_global_memory(
            user_id,
            f"## 历史对话摘要\n{conversation_summary}\n"
        )
        logging.info(
            f"[UserMemory] Preferences extracted and saved for user {user_id}"
        )


# 全局单例
_user_memory_service: Optional[UserMemoryService] = None


def get_user_memory_service(base_dir: str = "saves/memory") -> UserMemoryService:
    """获取用户记忆服务单例
    
    Args:
        base_dir: 基础存储目录
        
    Returns:
        UserMemoryService 实例
    """
    global _user_memory_service
    if _user_memory_service is None:
        _user_memory_service = UserMemoryService(base_dir)
    return _user_memory_service
