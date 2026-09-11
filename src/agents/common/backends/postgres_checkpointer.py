"""PostgreSQL Checkpointer Backend - LangGraph 状态持久化

使用 AsyncConnectionPool + AsyncPostgresSaver 实现 LangGraph 状态的持久化存储。

⚠️ 为什么必须用连接池：
`AsyncPostgresSaver.from_conn_string()` 只持有一条 psycopg AsyncConnection，
而 LangGraph 在 astream() 执行期间（以及多请求并发时）会并发访问 checkpointer
（aget_tuple / aput / aput_writes），单条 AsyncConnection 不允许命令并发，
必然抛出 `psycopg.OperationalError: another command is already in progress`，
导致整个 SSE 流中断——表现为「前端显示正在生成，随后无声停止、无任何回复」。

改用 AsyncConnectionPool 后每个并发操作各自取用独立连接，彻底规避该问题。

核心优势：
1. 自动保存：每次 Agent 执行完毕后自动保存状态
2. 历史加载：下次调用时自动加载该 thread_id 的所有历史消息
3. 分支管理：支持对话分支（用于探索不同可能性）
4. 压缩策略：当消息过长时自动触发摘要压缩
"""
import logging
import os
from typing import Optional

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool


class PostgresCheckpointerBackend:
    """基于 PostgreSQL 的 LangGraph 状态持久化（连接池版）

    单例模式：确保全局只有一个 checkpointer 实例，避免重复建池。
    """

    _instance: Optional["PostgresCheckpointerBackend"] = None

    def __init__(self, conn_string: str):
        """初始化 PostgreSQL Checkpointer

        Args:
            conn_string: PostgreSQL 连接字符串
                格式: "postgresql://user:password@host:port/dbname"
        """
        self._conn_string = conn_string
        self._initialized = False
        self._checkpointer: Optional[AsyncPostgresSaver] = None
        self._pool: Optional[AsyncConnectionPool] = None

    @classmethod
    def get_instance(cls, conn_string: str) -> "PostgresCheckpointerBackend":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(conn_string)
        return cls._instance

    async def get_checkpointer(self) -> AsyncPostgresSaver:
        """获取或创建 AsyncPostgresSaver 实例（懒加载）"""
        if self._checkpointer is None:
            await self._initialize()
        return self._checkpointer

    async def _initialize(self):
        """初始化连接池 + AsyncPostgresSaver

        要点：
        1. 池必须以 open=False 创建，再在事件循环内 await pool.open()，
           避免在 import / 非事件循环上下文提前连库。
        2. AsyncPostgresSaver 直接接 pool，不要再调 from_conn_string。
        3. setup() 幂等建表（checkpoints / checkpoint_writes / checkpoint_blobs）。
        """
        try:
            logging.info("[PostgresCheckpointer] Initializing (pool mode)...")

            # 池大小：并发请求 + 单请求内并发操作都需要独立连接，留足余量
            pool_min = int(os.getenv("PG_CHECKPOINTER_POOL_MIN", "4"))
            pool_max = int(os.getenv("PG_CHECKPOINTER_POOL_MAX", "20"))
            pool_timeout = float(os.getenv("PG_CHECKPOINTER_POOL_TIMEOUT", "30"))

            self._pool = AsyncConnectionPool(
                conninfo=self._conn_string,
                min_size=pool_min,
                max_size=pool_max,
                open=False,                 # 关键：延迟到事件循环内开启
                timeout=pool_timeout,
                kwargs={
                    # prepared statement 会在连接复用/跨连接时冲突，关闭之
                    "autocommit": True,
                    "prepare_threshold": None,
                    # 长事务（Agent 流式执行）需要足够的语句超时
                    "options": "-c statement_timeout=0",
                },
            )
            await self._pool.open()
            await self._pool.wait()

            self._checkpointer = AsyncPostgresSaver(self._pool)
            await self._checkpointer.setup()

            self._initialized = True
            logging.info(
                f"[PostgresCheckpointer] ✅ Initialized successfully "
                f"(pool min={pool_min}, max={pool_max})"
            )

        except Exception as e:
            logging.error(f"[PostgresCheckpointer] ❌ Initialization failed: {e}")
            # 初始化失败时清理半成品池，避免泄漏
            if self._pool is not None:
                try:
                    await self._pool.close()
                except Exception:
                    pass
                self._pool = None
            raise

    async def close(self):
        """关闭连接池"""
        if self._pool is not None:
            try:
                await self._pool.close()
            except Exception as e:
                logging.warning(f"[PostgresCheckpointer] Error during close: {e}")
            self._pool = None
            self._checkpointer = None
            self._initialized = False
            logging.info("[PostgresCheckpointer] Pool closed")

    def is_initialized(self) -> bool:
        """检查是否已初始化"""
        return self._initialized


# 全局单例访问函数
def get_postgres_checkpointer(conn_string: str) -> PostgresCheckpointerBackend:
    """获取 PostgreSQL Checkpointer 单例"""
    return PostgresCheckpointerBackend.get_instance(conn_string)
