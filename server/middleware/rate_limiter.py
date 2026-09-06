"""速率限制依赖 — 基于 Redis 滑动窗口"""

import logging
from typing import Optional

from fastapi import Depends, HTTPException, Request

from server.utils.auth_middleware import get_required_user
from src.services.redis_cache import get_redis_cache


class RateLimiter:
    """速率限制器

    用法（FastAPI 依赖注入）:
        @router.post("/chat")
        async def chat(
            rate_limiter: RateLimiter = Depends(get_rate_limiter),
        ):
            await rate_limiter.check("chat", max_requests=5, window=60)
    """

    def __init__(self):
        self._cache = get_redis_cache()
        self._available = False

    async def _ensure_available(self):
        if not self._cache._connected:
            try:
                await self._cache.connect()
            except Exception:
                pass
        self._available = self._cache._connected

    async def check(
        self,
        identifier: str,
        max_requests: int = 10,
        window: int = 60,
    ) -> None:
        """检查速率限制，超限抛出 429

        Args:
            identifier: 标识符（如 user:{user_id}:chat）
            max_requests: 时间窗口内最大请求数
            window: 时间窗口（秒）
        """
        await self._ensure_available()
        if not self._available:
            return  # Redis 不可用时长驱直入

        allowed = await self._cache.check_rate_limit(identifier, max_requests, window)
        if not allowed:
            remaining = await self._cache.get_rate_limit_remaining(identifier, max_requests, window)
            raise HTTPException(
                status_code=429,
                detail={
                    "error": "rate_limit_exceeded",
                    "message": f"请求过于频繁，请在 {window} 秒后重试",
                    "retry_after": window,
                    "remaining": remaining,
                },
            )

    async def get_remaining(self, identifier: str, max_requests: int = 10, window: int = 60) -> int:
        """获取剩余配额"""
        await self._ensure_available()
        if not self._available:
            return max_requests
        return await self._cache.get_rate_limit_remaining(identifier, max_requests, window)


# 全局单例
_rate_limiter: Optional[RateLimiter] = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter


async def rate_limit_dependency(request: Request) -> RateLimiter:
    """FastAPI 依赖：自动使用用户 ID 作为限流标识"""
    limiter = get_rate_limiter()
    # 尝试获取用户 ID
    try:
        user = await get_required_user(request)
        identifier = f"api:user:{user.id}:global"
    except Exception:
        # 未认证用户，使用 IP
        identifier = f"api:ip:{request.client.host if request.client else 'unknown'}:global"
    await limiter.check(identifier, max_requests=60, window=60)
    return limiter
