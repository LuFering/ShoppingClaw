"""通用缓存装饰器 — 基于 Redis 缓存函数结果"""

import asyncio
import hashlib
import json
import logging
from functools import wraps
from typing import Callable

from src.services.redis_cache import get_redis_cache

logger = logging.getLogger(__name__)


def _make_cache_key(prefix: str, *args, **kwargs) -> str:
    """基于参数生成唯一缓存键"""
    raw = json.dumps({"args": args, "kwargs": kwargs}, sort_keys=True, ensure_ascii=False, default=str)
    h = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"cache:{prefix}:{h}"


def redis_cache(
    ttl: int = 300,
    prefix: str = "func",
    enabled: bool = True,
    skip_args: tuple = (),
):
    """Redis 缓存装饰器 — 支持同步和异步函数

    Args:
        ttl: 缓存过期时间（秒），默认 5 分钟
        prefix: 缓存键前缀，用于区分不同函数
        enabled: 是否启用缓存
        skip_args: 跳过哪些参数名（不参与缓存键计算）

    用法:
        @redis_cache(ttl=600, prefix="jd_search")
        def jd_deep_search(keyword, max_pages=3):
            ...
    """
    def decorator(func: Callable):
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            if not enabled:
                return func(*args, **kwargs)

            # 过滤掉要跳过的参数
            cache_kwargs = {k: v for k, v in kwargs.items() if k not in skip_args}
            cache_key = _make_cache_key(prefix, *args, **cache_kwargs)

            cache = get_redis_cache()
            try:
                # 同步路径使用独立短连接（RedisCache.sync_get/sync_set），
                # 绝不访问绑定 serve 事件循环的共享连接池，
                # 避免 "Lock bound to a different event loop" 跨循环错误。
                cached = cache.sync_get(cache_key)
                if cached is not None:
                    logger.info(f"[Cache] HIT  {cache_key}")
                    return cached

                result = func(*args, **kwargs)

                # 异步保存缓存（独立连接，失败不影响业务）
                cache.sync_set(cache_key, result, ttl)

                logger.info(f"[Cache] MISS {cache_key} → cached (ttl={ttl}s)")
                return result

            except Exception as e:
                logger.warning(f"[Cache] 缓存操作失败，直接执行: {e}")
                return func(*args, **kwargs)

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            if not enabled:
                return await func(*args, **kwargs)

            cache_kwargs = {k: v for k, v in kwargs.items() if k not in skip_args}
            cache_key = _make_cache_key(prefix, *args, **cache_kwargs)

            cache = get_redis_cache()
            try:
                await _ensure_redis(cache)
                if cache._connected:
                    cached = await _get_cache_async(cache, cache_key)
                    if cached is not None:
                        logger.info(f"[Cache] HIT  {cache_key}")
                        return cached

                    result = await func(*args, **kwargs)
                    await _set_cache_async(cache, cache_key, result, ttl)
                    logger.info(f"[Cache] MISS {cache_key} → cached (ttl={ttl}s)")
                    return result
            except Exception as e:
                logger.warning(f"[Cache] 缓存操作失败，直接执行: {e}")

            return await func(*args, **kwargs)

        # 根据原函数类型返回对应 wrapper
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


async def _ensure_redis(cache):
    if not cache._connected:
        try:
            await cache.connect()
        except Exception:
            pass


async def _get_cache_async(cache, key):
    try:
        return await cache.get(key)
    except Exception:
        return None


async def _set_cache_async(cache, key, value, ttl):
    try:
        await cache.set(key, value, ttl=ttl)
    except Exception:
        pass


def invalidate_cache_prefix(prefix: str) -> int:
    """清除指定前缀的所有缓存（异步版本请用 async_invalidate_cache_prefix）"""
    import asyncio as _asyncio
    return _asyncio.run(async_invalidate_cache_prefix(prefix))


async def async_invalidate_cache_prefix(prefix: str) -> int:
    """异步清除指定前缀的 Redis 缓存"""
    cache = get_redis_cache()
    await _ensure_redis(cache)
    if not cache._connected:
        return 0

    pattern = f"cache:{prefix}:*"
    count = 0
    try:
        async for key in cache._redis.scan_iter(match=pattern):
            await cache._redis.delete(key)
            count += 1
    except Exception as e:
        logger.warning(f"[Cache] 清除缓存失败: {e}")

    if count > 0:
        logger.info(f"[Cache] 清除 {count} 条缓存 (prefix={prefix})")
    return count
