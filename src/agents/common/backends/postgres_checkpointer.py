"""PostgreSQL Checkpointer Backend - LangGraph 状态持久化

参考 ScienceClaw 设计，使用 AsyncPostgresSaver 实现 LangGraph 状态的持久化存储。

核心优势：
1. 自动保存：每次 Agent 执行完毕后自动保存状态
2. 历史加载：下次调用时自动加载该 thread_id 的所有历史消息
3. 分支管理：支持对话分支（用于探索不同可能性）
4. 压缩策略：当消息过长时自动触发摘要压缩
"""
import logging
from typing import Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


class PostgresCheckpointerBackend:
    """基于 PostgreSQL 的 LangGraph 状态持久化

    单例模式：确保全局只有一个 checkpointer 实例，避免重复连接

    注意：AsyncPostgresSaver.from_conn_string() 返回的是异步上下文管理器
    (_AsyncGeneratorContextManager)，必须通过 __aenter__/__aexit__ 管理生命周期。
    """

    _instance: Optional["PostgresCheckpointerBackend"] = None
    _checkpointer: Optional[AsyncPostgresSaver] = None
    _checkpointer_cm = None  # 异步上下文管理器引用，用于 cleanup

    def __init__(self, conn_string: str):
        """初始化 PostgreSQL Checkpointer

        Args:
            conn_string: PostgreSQL 连接字符串
                格式: "postgresql://user:password@host:port/dbname"
        """
        self._conn_string = conn_string
        self._initialized = False

    @classmethod
    def get_instance(cls, conn_string: str) -> "PostgresCheckpointerBackend":
        """获取单例实例

        Args:
            conn_string: PostgreSQL 连接字符串

        Returns:
            PostgresCheckpointerBackend 实例
        """
        if cls._instance is None:
            cls._instance = cls(conn_string)
        return cls._instance

    async def get_checkpointer(self) -> AsyncPostgresSaver:
        """获取或创建 AsyncPostgresSaver 实例

        懒加载模式：首次调用时才初始化数据库连接和表结构

        Returns:
            AsyncPostgresSaver 实例
        """
        if self._checkpointer is None:
            await self._initialize()
        return self._checkpointer

    async def _initialize(self):
        """初始化 PostgreSQL Checkpointer

        AsyncPostgresSaver.from_conn_string() 返回异步上下文管理器，
        通过 __aenter__ 进入上下文获取实例后，必须显式调用 setup()
        创建 checkpoints 等表结构（__aenter__ 本身不会建表）。
        """
        try:
            logging.info("[PostgresCheckpointer] Initializing...")

            # from_conn_string 返回 _AsyncGeneratorContextManager，不是 AsyncPostgresSaver
            self._checkpointer_cm = AsyncPostgresSaver.from_conn_string(
                self._conn_string
            )
            # 通过 __aenter__ 进入上下文，获取真正的 AsyncPostgresSaver 实例
            self._checkpointer = await self._checkpointer_cm.__aenter__()

            # 显式建表：checkpoints / checkpoint_writes / checkpoint_blobs
            # （空库首启必需；已有表时 setup 为幂等操作）
            await self._checkpointer.setup()

            self._initialized = True
            logging.info("[PostgresCheckpointer] ✅ Initialized successfully")

        except Exception as e:
            logging.error(f"[PostgresCheckpointer] ❌ Initialization failed: {e}")
            raise

    async def close(self):
        """关闭数据库连接"""
        if self._checkpointer_cm:
            try:
                await self._checkpointer_cm.__aexit__(None, None, None)
            except Exception as e:
                logging.warning(f"[PostgresCheckpointer] Error during close: {e}")
            self._checkpointer = None
            self._checkpointer_cm = None
            self._initialized = False
            logging.info("[PostgresCheckpointer] Connection closed")

    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized


# 全局单例访问函数
def get_postgres_checkpointer(conn_string: str) -> PostgresCheckpointerBackend:
    """获取 PostgreSQL Checkpointer 单例

    Args:
        conn_string: PostgreSQL 连接字符串

    Returns:
        PostgresCheckpointerBackend 实例
    """
    return PostgresCheckpointerBackend.get_instance(conn_string)
