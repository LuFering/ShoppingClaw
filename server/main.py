"""
ShoppingClaw API Server
FastAPI 应用入口
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.routers import router
from server.routers.chat_rounter import chat
from src.storage.postgres.manager import pg_manager

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    logger.info("[START] ShoppingClaw API starting...")
    
    # 初始化数据库连接
    try:
        pg_manager.initialize()
        logger.info("[OK] Database connection established")
    except Exception as e:
        logger.error(f"[ERROR] Failed to initialize database: {e}")
        raise
    
    logger.info("[OK] ShoppingClaw API ready")
    
    yield
    
    # 关闭时执行
    logger.info("[STOP] ShoppingClaw API shutting down...")
    await pg_manager.close()
    logger.info("[OK] ShoppingClaw API stopped")


# 创建 FastAPI 应用
app = FastAPI(
    title="ShoppingClaw API",
    description="Deep Agents Shopping Agent - 智能购物助手 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# 注册路由
app.include_router(router, prefix="/api")
# 配置 CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应该限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 健康检查端点
@app.get("/api/system/health")
async def health_check():
    """健康检查接口"""
    return {
        "status": "healthy",
        "service": "ShoppingClaw API"
    }


# 根路径
@app.get("/")
async def root():
    """根路径"""
    return {
        "message": "Welcome to ShoppingClaw API",
        "docs": "/docs",
        "health": "/api/system/health"
    }


# 简单测试接口（不需要数据库）
@app.post("/api/test/echo")
async def test_echo(message: str = "Hello"):
    """简单的回声测试接口"""
    return {
        "status": "ok",
        "received": message,
        "timestamp": "2026-04-07T00:00:00Z"
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "server.main:app",
        host="0.0.0.0",
        port=5050,
        reload=True,
        log_level="info"
    )
