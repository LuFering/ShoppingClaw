"""
ShoppingClaw API Server
FastAPI 应用入口 — 精简版
"""
import asyncio
import logging
import os
import sys
import warnings

# 屏蔽 Pydantic 序列化警告（LangGraph 的 context 序列化时对 dataclass 不兼容）
warnings.filterwarnings("ignore", message="Pydantic serializer warnings")

# 确保 src/ 路径在 Python 搜索路径中，使 import jd 等模块正常工作
_src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src')
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.routers import router
from server.routers.auth_router import auth as auth_router
from server.routers.models_router import router as models_router
from server.routers.task_router import router as task_router
from server.middleware.audit import AuditMiddleware

# ── 日志系统：loguru 接管（文件落盘 saves/logs/ + 轮转保留 + 根 logger 桥接 + request_id）──
from src.utils.logging_config import logger, request_id_var

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("[START] ShoppingClaw API starting...")

    # 确保 saves 目录存在
    os.makedirs("saves", exist_ok=True)

    # Phase 1: 快速就绪（DB + 基础路由）
    from src.storage.postgres.manager import pg_manager
    try:
        pg_manager.initialize()
        await pg_manager.create_business_tables()
        logger.info("[OK] PostgreSQL initialized and tables created")
    except Exception as e:
        logger.warning(f"[WARN] PostgreSQL initialization failed: {e}")

    logger.info("[OK] API ready (models loading in background)")

    # Phase 1.3: 预热 Redis 连接（在 serve 事件循环内创建连接池，
    # 避免后续同步路径/其它循环先建连导致 "Lock bound to a different event loop"）
    from src.services.redis_cache import get_redis_cache
    try:
        await get_redis_cache().connect()
        logger.info("[OK] Redis connected (pre-warmed)")
    except Exception as e:
        logger.warning(f"[WARN] Redis pre-warm failed (cache/stores will degrade): {e}")

    # Phase 1.5: 初始化知识库（LlamaIndex + ChromaDB + DashScope Embedding）
    # 失败不阻塞启动，检索工具会走"暂未找到"兜底文案
    try:
        from src.knowledge.manager import knowledge_manager
        docs_dir = os.getenv("KNOWLEDGE_DOCS_DIR") or os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "docs", "knowledge"
        )
        await knowledge_manager.initialize(docs_dir)
        logger.info("[OK] Knowledge base initialized from %s", docs_dir)
    except Exception as e:
        logger.warning(f"[WARN] Knowledge base initialization failed: {e}")

    # Phase 2: 后台加载 ML 模型（不阻塞就绪）
    asyncio.create_task(warmup_models())

    # Phase 3: 启动定时任务调度器
    from src.services.scheduler_service import get_scheduler
    from src.services.task_executors import EXECUTORS

    scheduler = get_scheduler()
    for task_type, executor in EXECUTORS.items():
        scheduler.register_executor(task_type, executor)
    await scheduler.start()
    logger.info("[OK] Scheduler started with executors: %s", list(EXECUTORS.keys()))

    # Phase 4: 启动 SSE 会话清理任务（每小时清理不活跃的会话）
    cleanup_task = asyncio.create_task(_periodic_session_cleanup(interval=3600))

    yield

    # 停止调度器
    await scheduler.shutdown()

    # 停止清理任务
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass

    logger.info("[STOP] ShoppingClaw API shutting down...")
    
    # 清理 Redis 连接
    from src.services.redis_cache import get_redis_cache
    try:
        cache = get_redis_cache()
        await cache.disconnect()
        logger.info("[OK] Redis disconnected")
    except Exception as e:
        logger.warning(f"[WARN] Redis disconnect failed: {e}")


async def warmup_models():
    """后台加载 ML 模型"""
    try:
        from src.services.intent_service import get_intent_service
        await asyncio.to_thread(get_intent_service)
        logger.info("[OK] Intent detection model loaded")
    except Exception as e:
        logger.warning(f"[WARN] Intent detection model load failed: {e}")


async def _periodic_session_cleanup(interval: int = 3600):
    """定期清理不活跃的 SSE 会话（每小时一次）"""
    from src.services.sse_session_manager import get_session_manager
    while True:
        try:
            await asyncio.sleep(interval)
            manager = get_session_manager()
            manager.cleanup_inactive_sessions(max_age=3600)
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"[WARN] Session cleanup failed: {e}")


app = FastAPI(
    title="ShoppingClaw API",
    description="智能购物助手 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS — allow_origins 与 allow_credentials 不允许同时使用通配符
# 配置允许的来源列表
_allowed_origins = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://127.0.0.1:5173"
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in _allowed_origins if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 审计日志中间件
app.add_middleware(AuditMiddleware, enable_audit=True)


# ── 请求 ID 贯通：生成/透传 X-Request-ID，loguru 输出自动携带 ──
import uuid  # noqa: E402

from starlette.middleware.base import BaseHTTPMiddleware  # noqa: E402


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        rid = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = rid
        token = request_id_var.set(rid)
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        response.headers["X-Request-ID"] = rid
        return response


app.add_middleware(RequestIDMiddleware)


# ── 审计日志查询端点（管理员）──
from server.utils.auth_middleware import get_admin_user  # noqa: E402


@app.get("/api/system/audit-logs")
async def audit_logs(
    limit: int = 50,
    path_filter: str = None,
    current_user=Depends(get_admin_user),
):
    """查询操作审计日志（管理员）"""
    from src.repositories.operation_log_repository import OperationLogRepository
    repo = OperationLogRepository()
    rows = await repo.list_logs(limit=limit, path_filter=path_filter)
    return {"success": True, "data": rows, "total": len(rows)}


# 注册路由
app.include_router(router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(models_router, prefix="/api")
app.include_router(task_router, prefix="/api")


@app.get("/api/system/health")
async def health_check():
    return {"status": "ok", "service": "ShoppingClaw API"}


@app.get("/api/system/info")
async def system_info():
    return {
        "success": True,
        "data": {
            "organization": {
                "name": "ShoppingClaw",
                "logo": "/logo.png",
                "avatar": "/avatar.png",
            },
            "branding": {
                "name": "ShoppingClaw",
                "title": "ShoppingClaw",
                "subtitle": "智能购物助手",
            },
            "features": [],
            "actions": [],
            "footer": {
                "copyright": "© 2026 ShoppingClaw. All rights reserved."
            },
        },
    }


@app.get("/")
async def root():
    return {
        "message": "Welcome to ShoppingClaw API",
        "docs": "/docs",
        "health": "/api/system/health",
    }


@app.post("/api/test/echo")
async def test_echo(message: str = "Hello"):
    return {"status": "ok", "received": message, "timestamp": "2026-04-07T00:00:00Z"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=5050,
        reload=True,
        log_level="info",
    )
