"""
断路器 - 参考 ScienceClaw 的 CircuitBreaker

防止连续失败导致系统雪崩。当某个操作连续失败 N 次后，
断路器打开，在冷却时间内直接返回 fallback，不再执行实际操作。
"""
import asyncio
from src.utils.loop_safe_lock import loop_safe
import logging
import time
from typing import Any, Callable, Optional


class CircuitBreaker:
    """
    断路器模式实现
    
    状态机:
    - CLOSED（关闭）: 正常执行，失败计数 < threshold
    - OPEN（打开）: 拒绝执行，直接返回 fallback
    - HALF-OPEN（半开）: 允许一次试探性执行
    
    使用方式:
    ```python
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30)
    
    async def call_external_api():
        return await breaker.call(
            coro=fetch_data(),
            fallback={"error": "Service unavailable"}
        )
    ```
    """
    
    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        name: str = "default",
    ):
        """
        初始化断路器
        
        Args:
            failure_threshold: 失败阈值（连续失败 N 次后打开）
            cooldown_seconds: 冷却时间（秒），之后进入半开状态
            name: 断路器名称（用于日志）
        """
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self.name = name
        
        # 状态变量
        self._failure_count = 0
        self._last_failure_time: float = 0
        self._state = "CLOSED"  # CLOSED | OPEN | HALF-OPEN
        self._lock = asyncio.Lock()
        
        # 统计信息
        self._total_calls = 0
        self._total_failures = 0
        self._total_rejected = 0
    
    async def call(self, coro: Any, fallback: Any = None) -> Any:
        """
        通过断路器执行协程
        
        Args:
            coro: 要执行的协程
            fallback: 断路器打开时的降级返回值
            
        Returns:
            协程的执行结果或 fallback
            
        Raises:
            Exception: 如果断路器关闭且执行失败
        """
        async with loop_safe(self._lock):
            self._total_calls += 1
            
            # 检查是否应该打开断路器
            if self._is_open():
                # 检查是否可以进入半开状态
                if self._should_attempt_reset():
                    self._state = "HALF-OPEN"
                    logging.info(
                        f"[CircuitBreaker:{self.name}] Transitioning to HALF-OPEN state"
                    )
                else:
                    # 断路器仍然打开，返回 fallback
                    self._total_rejected += 1
                    logging.warning(
                        f"[CircuitBreaker:{self.name}] Circuit is OPEN, returning fallback"
                    )
                    return fallback
        
        # 执行协程（在锁外执行，避免阻塞）
        try:
            result = await coro
            
            # 执行成功，重置计数器
            await self._on_success()
            
            return result
            
        except Exception as e:
            # 执行失败，记录失败
            await self._on_failure(e)
            
            # 如果有 fallback，返回 fallback
            if fallback is not None:
                return fallback
            
            # 否则抛出异常
            raise
    
    async def _on_success(self):
        """处理成功调用"""
        async with loop_safe(self._lock):
            self._failure_count = 0
            self._state = "CLOSED"
            logging.debug(
                f"[CircuitBreaker:{self.name}] Call succeeded, resetting counter"
            )
    
    async def _on_failure(self, error: Exception):
        """处理失败调用"""
        async with loop_safe(self._lock):
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            self._total_failures += 1
            
            # 检查是否达到阈值
            if self._failure_count >= self.failure_threshold:
                self._state = "OPEN"
                logging.warning(
                    f"[CircuitBreaker:{self.name}] Circuit OPENED after "
                    f"{self._failure_count} failures"
                )
            else:
                logging.debug(
                    f"[CircuitBreaker:{self.name}] Failure {self._failure_count}/"
                    f"{self.failure_threshold}"
                )
    
    def _is_open(self) -> bool:
        """检查断路器是否打开"""
        return self._state == "OPEN"
    
    def _should_attempt_reset(self) -> bool:
        """检查是否应该尝试重置（进入半开状态）"""
        elapsed = time.monotonic() - self._last_failure_time
        return elapsed > self.cooldown_seconds
    
    def get_state(self) -> dict:
        """
        获取断路器当前状态
        
        Returns:
            状态字典
        """
        return {
            "name": self.name,
            "state": self._state,
            "failure_count": self._failure_count,
            "failure_threshold": self.failure_threshold,
            "cooldown_seconds": self.cooldown_seconds,
            "last_failure_time": self._last_failure_time,
            "stats": {
                "total_calls": self._total_calls,
                "total_failures": self._total_failures,
                "total_rejected": self._total_rejected,
                "success_rate": (
                    (self._total_calls - self._total_failures) / self._total_calls
                    if self._total_calls > 0
                    else 0
                ),
            },
        }
    
    def reset(self):
        """手动重置断路器"""
        self._failure_count = 0
        self._last_failure_time = 0
        self._state = "CLOSED"
        logging.info(f"[CircuitBreaker:{self.name}] Manually reset")


class CircuitBreakerManager:
    """
    断路器管理器
    
    管理多个断路器实例，按名称访问。
    
    使用方式:
    ```python
    manager = CircuitBreakerManager()
    
    # 获取或创建断路器
    breaker = manager.get_breaker(
        name="jd_api",
        failure_threshold=3,
        cooldown_seconds=30
    )
    
    # 使用断路器
    result = await breaker.call(coro=fetch_jd_data(), fallback={})
    ```
    """
    
    def __init__(self):
        self._breakers: dict[str, CircuitBreaker] = {}
        self._lock = asyncio.Lock()
    
    async def get_breaker(
        self,
        name: str,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
    ) -> CircuitBreaker:
        """
        获取或创建断路器
        
        Args:
            name: 断路器名称
            failure_threshold: 失败阈值
            cooldown_seconds: 冷却时间
            
        Returns:
            CircuitBreaker 实例
        """
        if name not in self._breakers:
            async with loop_safe(self._lock):
                # 双重检查锁定
                if name not in self._breakers:
                    self._breakers[name] = CircuitBreaker(
                        failure_threshold=failure_threshold,
                        cooldown_seconds=cooldown_seconds,
                        name=name,
                    )
                    logging.info(
                        f"[CircuitBreakerManager] Created breaker: {name}"
                    )
        
        return self._breakers[name]
    
    async def get_all_states(self) -> dict:
        """获取所有断路器的状态"""
        states = {}
        for name, breaker in self._breakers.items():
            states[name] = breaker.get_state()
        return states
    
    async def reset_all(self):
        """重置所有断路器"""
        for breaker in self._breakers.values():
            breaker.reset()
        logging.info("[CircuitBreakerManager] Reset all breakers")


# 全局单例
_circuit_breaker_manager: CircuitBreakerManager | None = None


async def get_circuit_breaker_manager() -> CircuitBreakerManager:
    """获取全局 CircuitBreakerManager 实例"""
    global _circuit_breaker_manager
    if _circuit_breaker_manager is None:
        _circuit_breaker_manager = CircuitBreakerManager()
    return _circuit_breaker_manager


async def get_circuit_breaker(
    name: str,
    failure_threshold: int = 3,
    cooldown_seconds: float = 30.0,
) -> CircuitBreaker:
    """
    便捷函数：获取断路器
    
    Args:
        name: 断路器名称
        failure_threshold: 失败阈值
        cooldown_seconds: 冷却时间
        
    Returns:
        CircuitBreaker 实例
    """
    manager = await get_circuit_breaker_manager()
    return await manager.get_breaker(
        name=name,
        failure_threshold=failure_threshold,
        cooldown_seconds=cooldown_seconds,
    )
