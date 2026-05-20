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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.routers import router
from server.routers.auth_router import auth as auth_router
from server.routers.models_router import router as models_router
from server.middleware.audit import AuditMiddleware

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
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

    # Phase 2: 后台加载 ML 模型（不阻塞就绪）
    asyncio.create_task(warmup_models())

    # Phase 3: 启动 SSE 会话清理任务（每小时清理不活跃的会话）
    cleanup_task = asyncio.create_task(_periodic_session_cleanup(interval=3600))

    yield

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

# 注册路由
app.include_router(router, prefix="/api")
app.include_router(auth_router, prefix="/api")
app.include_router(models_router, prefix="/api")


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
