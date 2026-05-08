"""数据库管理器,执行建表操作"""
import json
import logging
import os
from contextlib import asynccontextmanager
from .models_business import Base as BusinessBase
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession

from server.utils.singleton import SingletonMeta


class PostgresManager(metaclass=SingletonMeta):
    """PostgreSQL 数据库管理器"""
    # 知识库 PostgreSQL URL 环境变量名
    KB_DATABASE_URL_ENV = "POSTGRES_URL"

    def __init__(self):
        self.async_engine = None
        self.AsyncSession = None
        self._initialized = False

    def initialize(self):
        """初始化数据库连接"""
        if self._initialized:
            return
        db_url=os.getenv(self.KB_DATABASE_URL_ENV)
        if not db_url:
            logging.error(
                f"环境变量 {self.KB_DATABASE_URL_ENV} 未设置，"
                "请在 docker-compose.yml 或 .env 中配置 PostgreSQL 连接字符串"
            )
            return
        try:
            # 创建异步 SQLAlchemy 引擎
            self.async_engine = create_async_engine(
                db_url,
                json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
                json_deserializer=json.loads,
                pool_pre_ping=True,
                pool_recycle=1800,
            )

            # 创建异步会话工厂
            self.AsyncSession = async_sessionmaker(
                bind=self.async_engine,
                class_=AsyncSession,
                expire_on_commit=False,
            )

            self._initialized = True
            logging.info(f"PostgreSQL manager initialized for knowledge base: {db_url.split('@')[0]}://***")
        except Exception as e:
            logging.error(f"Failed to initialize PostgreSQL manager: {e}")
            # 不抛出异常，允许应用启动，但在使用时会报错
    def _check_initialized(self):
        """检查是否已初始化"""
        if not self._initialized:
            raise RuntimeError("PostgreSQL manager not initialized. Please check configuration.")

    async def create_business_tables(self):
        """创建业务表"""
        self._check_initialized()
        async with self.async_engine.begin() as conn:
            await conn.run_sync(BusinessBase.metadata.create_all)
        logging.info("PostgreSQL tables created/checked  business")

    @asynccontextmanager
    async def get_async_session_context(self):
        """获取异步数据库会话的上下文管理器"""
        self._check_initialized()
        session = self.AsyncSession()
        try:
            yield session
            await session.commit()
        except Exception as e:
            await session.rollback()
            logging.error(f"PostgreSQL async operation failed: {e}")
            raise
        finally:
            await session.close()

    async def close(self):
        """关闭引擎"""
        if self.async_engine:
            await self.async_engine.dispose()

    async def async_check_first_run(self):
        """检查是否首次运行（异步版本）- 检查用户表是否有数据"""
        from sqlalchemy import func, select

        self._check_initialized()
        async with self.get_async_session_context() as session:
            from src.storage.postgres.models_business import User

            result = await session.execute(select(func.count(User.id)))
            count = result.scalar()
            return count == 0

    async def execute(self, statement):
        """直接执行 SQL 语句（用于迁移脚本）"""
        self._check_initialized()
        async with self.get_async_session_context() as session:
            return await session.execute(statement)

    async def add(self, instance):
        """添加实例到会话（用于迁移脚本）"""
        self._check_initialized()
        async with self.get_async_session_context() as session:
            session.add(instance)

    async def commit(self):
        """提交当前会话"""
        self._check_initialized()
        async with self.get_async_session_context():
            pass  # commit is automatic in context manager


pg_manager = PostgresManager()
