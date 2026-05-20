"""
Redis 缓存层 - 参考 ScienceClaw 的 CacheBackend

提供统一的 Redis 缓存接口，支持：
- 会话缓存（带 TTL）
- 速率限制
- 通用键值缓存
"""
import asyncio
import json
import logging
import os
import time
from typing import Any, Optional

import redis.asyncio as redis


class RedisCache:
    """
    Redis 缓存管理器
    
    功能:
    1. 会话缓存（替代进程内 memory_store）
    2. 速率限制（基于滑动窗口）
    3. 通用键值缓存
    4. 发布/订阅（多实例事件广播）
    
    使用方式:
    ```python
    from src.services.redis_cache import get_redis_cache
    
    cache = get_redis_cache()
    
    # 设置缓存
    await cache.set("user:123:session", session_data, ttl=3600)
    
    # 获取缓存
    session = await cache.get("user:123:session")
    
    # 速率限制
    is_allowed = await cache.check_rate_limit("user:123", max_requests=10, window=60)
    ```
    """
    
    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        """
        初始化 Redis 缓存
        
        Args:
            redis_url: Redis 连接 URL
        """
        self.redis_url = redis_url
        self._redis: redis.Redis | None = None
        self._connected = False
    
    async def connect(self):
        """连接到 Redis"""
        if not self._connected:
            try:
                self._redis = redis.from_url(
                    self.redis_url,
                    encoding="utf-8",
                    decode_responses=True,
                )
                
                # 测试连接
                await self._redis.ping()
                
                self._connected = True
                logging.info(f"[RedisCache] Connected to {self.redis_url}")
            
            except Exception as e:
                logging.error(f"[RedisCache] Failed to connect: {e}")
                self._connected = False
                raise
    
    async def disconnect(self):
        """断开 Redis 连接"""
        if self._redis:
            await self._redis.close()
            self._connected = False
            logging.info("[RedisCache] Disconnected")
    
    # ========== 基础缓存操作 ==========
    
    async def get(self, key: str) -> Any | None:
        """
        获取缓存值
        
        Args:
            key: 缓存键
            
        Returns:
            缓存值或 None
        """
        if not self._connected:
            await self.connect()
        
        try:
            value = await self._redis.get(key)
            
            if value is None:
                return None
            
            # 尝试解析 JSON
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        
        except Exception as e:
            logging.error(f"[RedisCache] GET failed for key {key}: {e}")
            return None
    
    async def set(self, key: str, value: Any, ttl: int | None = None):
        """
        设置缓存值
        
        Args:
            key: 缓存键
            value: 缓存值
            ttl: 过期时间（秒），None 表示永久
        """
        if not self._connected:
            await self.connect()
        
        try:
            # 序列化为 JSON
            if isinstance(value, (dict, list)):
                value_str = json.dumps(value, ensure_ascii=False)
            else:
                value_str = str(value)
            
            if ttl:
                await self._redis.setex(key, ttl, value_str)
            else:
                await self._redis.set(key, value_str)
        
        except Exception as e:
            logging.error(f"[RedisCache] SET failed for key {key}: {e}")
    
    async def delete(self, key: str) -> bool:
        """
        删除缓存
        
        Args:
            key: 缓存键
            
        Returns:
            是否删除成功
        """
        if not self._connected:
            await self.connect()
        
        try:
            result = await self._redis.delete(key)
            return result > 0
        
        except Exception as e:
            logging.error(f"[RedisCache] DELETE failed for key {key}: {e}")
            return False
    
    async def exists(self, key: str) -> bool:
        """
        检查键是否存在
        
        Args:
            key: 缓存键
            
        Returns:
            是否存在
        """
        if not self._connected:
            await self.connect()
        
        try:
            return await self._redis.exists(key) > 0
        
        except Exception as e:
            logging.error(f"[RedisCache] EXISTS failed for key {key}: {e}")
            return False
    
    # ========== 会话缓存 ==========
    
    async def get_session(self, session_id: str) -> dict | None:
        """
        获取会话数据
        
        Args:
            session_id: 会话 ID
            
        Returns:
            会话数据或 None
        """
        return await self.get(f"session:{session_id}")
    
    async def set_session(self, session_id: str, data: dict, ttl: int = 3600):
        """
        设置会话数据
        
        Args:
            session_id: 会话 ID
            data: 会话数据
            ttl: 过期时间（秒），默认 1 小时
        """
        await self.set(f"session:{session_id}", data, ttl=ttl)
    
    async def delete_session(self, session_id: str):
        """
        删除会话
        
        Args:
            session_id: 会话 ID
        """
        await self.delete(f"session:{session_id}")
    
    # ========== 速率限制 ==========
    
    async def check_rate_limit(
        self,
        identifier: str,
        max_requests: int = 10,
        window: int = 60,
    ) -> bool:
        """
        检查速率限制（滑动窗口算法）
        
        Args:
            identifier: 标识符（如用户 ID、IP）
            max_requests: 最大请求数
            window: 时间窗口（秒）
            
        Returns:
            是否允许请求
        """
        if not self._connected:
            await self.connect()
        
        key = f"rate_limit:{identifier}"
        now = time.time()
        window_start = now - window
        
        try:
            # 使用 pipeline 保证原子性
            pipe = self._redis.pipeline()
            
            # 移除过期记录
            pipe.zremrangebyscore(key, 0, window_start)
            
            # 添加当前请求
            pipe.zadd(key, {str(now): now})
            
            # 计算当前窗口内的请求数
            pipe.zcard(key)
            
            # 设置过期时间
            pipe.expire(key, window)
            
            # 执行
            results = await pipe.execute()
            
            # 最后一个结果是当前请求数
            current_count = results[-1]
            
            if current_count > max_requests:
                logging.warning(
                    f"[RedisCache] Rate limit exceeded for {identifier}: "
                    f"{current_count}/{max_requests} in {window}s"
                )
                return False
            
            return True
        
        except Exception as e:
            logging.error(f"[RedisCache] Rate limit check failed: {e}")
            return True  # 失败时放行
    
    async def get_rate_limit_remaining(
        self,
        identifier: str,
        max_requests: int = 10,
        window: int = 60,
    ) -> int:
        """
        获取剩余请求数
        
        Args:
            identifier: 标识符
            max_requests: 最大请求数
            window: 时间窗口（秒）
            
        Returns:
            剩余请求数
        """
        if not self._connected:
            await self.connect()
        
        key = f"rate_limit:{identifier}"
        now = time.time()
        window_start = now - window
        
        try:
            # 移除过期记录
            await self._redis.zremrangebyscore(key, 0, window_start)
            
            # 计算当前窗口内的请求数
            current_count = await self._redis.zcard(key)
            
            return max(0, max_requests - current_count)
        
        except Exception as e:
            logging.error(f"[RedisCache] Get rate limit remaining failed: {e}")
            return max_requests
    
    # ========== 发布/订阅 ==========
    
    async def publish(self, channel: str, message: dict):
        """
        发布消息到频道
        
        Args:
            channel: 频道名称
            message: 消息内容
        """
        if not self._connected:
            await self.connect()
        
        try:
            message_str = json.dumps(message, ensure_ascii=False)
            await self._redis.publish(channel, message_str)
        
        except Exception as e:
            logging.error(f"[RedisCache] Publish failed: {e}")
    
    async def subscribe(self, channel: str):
        """
        订阅频道
        
        Args:
            channel: 频道名称
            
        Returns:
            PubSub 对象
        """
        if not self._connected:
            await self.connect()
        
        pubsub = self._redis.pubsub()
        await pubsub.subscribe(channel)
        
        return pubsub
    
    # ========== 统计信息 ==========
    
    async def get_stats(self) -> dict:
        """
        获取 Redis 统计信息
        
        Returns:
            统计信息字典
        """
        if not self._connected:
            await self.connect()
        
        try:
            info = await self._redis.info()
            
            return {
                "connected": self._connected,
                "used_memory_human": info.get("used_memory_human", "N/A"),
                "connected_clients": info.get("connected_clients", 0),
                "total_commands_processed": info.get("total_commands_processed", 0),
                "keyspace_hits": info.get("keyspace_hits", 0),
                "keyspace_misses": info.get("keyspace_misses", 0),
                "hit_rate": (
                    info.get("keyspace_hits", 0) /
                    (info.get("keyspace_hits", 0) + info.get("keyspace_misses", 1))
                    if (info.get("keyspace_hits", 0) + info.get("keyspace_misses", 0)) > 0
                    else 0
                ),
            }
        
        except Exception as e:
            logging.error(f"[RedisCache] Get stats failed: {e}")
            return {"connected": False, "error": str(e)}


# 全局单例
_redis_cache: RedisCache | None = None


def get_redis_cache(redis_url: str | None = None) -> RedisCache:
    """
    获取全局 RedisCache 实例
    
    Args:
        redis_url: Redis 连接 URL（可选）
        
    Returns:
        RedisCache 实例
    """
    global _redis_cache
    
    if _redis_cache is None:
        url = redis_url or os.getenv("REDIS_URL", "redis://localhost:6379/0")
        _redis_cache = RedisCache(redis_url=url)
    
    return _redis_cache
