"""
重试中间件
"""
import asyncio
from functools import wraps


def retry(max_attempts: int = 3, delay: float = 1.0):
    """
    重试装饰器
    
    Args:
        max_attempts: 最大重试次数
        delay: 重试延迟（秒）
        
    Returns:
        装饰器函数
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # TODO: 实现重试逻辑
            pass
        return wrapper
    return decorator
