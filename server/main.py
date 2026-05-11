"""
ShoppingClaw API Server
FastAPI 应用入口 — 精简版
"""
import logging
import os
import sys

# 确保 src/ 路径在 Python 搜索路径中，使 import jd 等模块正常工作
_src_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'src')
if _src_path not in sys.path:
    sys.path.insert(0, _src_path)

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.routers import router
from server.routers.auth_router import auth as auth_router

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

    logger.info("[OK] ShoppingClaw API ready")
    yield
    logger.info("[STOP] ShoppingClaw API shutting down...")


app = FastAPI(
    title="ShoppingClaw API",
    description="智能购物助手 API",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(router, prefix="/api")
app.include_router(auth_router, prefix="/api")


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
