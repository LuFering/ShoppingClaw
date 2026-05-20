"""
审计日志中间件 - 参考 ScienceClaw 的 AuditMiddleware

记录所有 HTTP 请求的操作日志，包括：
- 用户 ID
- 请求路径和方法
- 响应状态码
- 耗时统计
- IP 地址
"""
import asyncio
import logging
import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from src.repositories.operation_log_repository import OperationLogRepository


class AuditMiddleware(BaseHTTPMiddleware):
    """
    审计日志中间件
    
    功能:
    1. 记录所有 HTTP 请求
    2. 异步写入数据库（不阻塞响应）
    3. 过滤健康检查等无关请求
    4. 支持敏感路径脱敏
    
    使用方式:
    ```python
    from server.middleware.audit import AuditMiddleware
    
    app.add_middleware(AuditMiddleware)
    ```
    """
    
    # 需要忽略的路径（不记录日志）
    IGNORED_PATHS = {
        "/api/system/health",
        "/api/system/info",
        "/docs",
        "/redoc",
        "/openapi.json",
        "/",
    }
    
    # 敏感路径（脱敏处理）
    SENSITIVE_PATHS = {
        "/api/auth/login",
        "/api/auth/register",
    }
    
    def __init__(self, app, enable_audit: bool = True):
        """
        初始化审计中间件
        
        Args:
            app: FastAPI 应用实例
            enable_audit: 是否启用审计日志
        """
        super().__init__(app)
        self.enable_audit = enable_audit
        self.repo = OperationLogRepository()
        
        if enable_audit:
            logging.info("[AuditMiddleware] Enabled")
        else:
            logging.info("[AuditMiddleware] Disabled")
    
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        处理请求并记录审计日志
        
        Args:
            request: HTTP 请求
            call_next: 下一个处理函数
            
        Returns:
            HTTP 响应
        """
        # 快速路径：如果禁用审计或忽略路径，直接处理
        if not self.enable_audit or request.url.path in self.IGNORED_PATHS:
            return await call_next(request)
        
        # 记录开始时间
        start_time = time.time()
        
        # 获取用户 ID（从认证中间件注入）
        user_id = getattr(request.state, "user_id", None)
        
        # 处理请求
        try:
            response = await call_next(request)
        except Exception as e:
            # 即使出错也记录日志
            duration_ms = int((time.time() - start_time) * 1000)
            
            # 异步记录错误日志
            asyncio.create_task(
                self._log_operation(
                    user_id=user_id,
                    path=request.url.path,
                    method=request.method,
                    status_code=500,
                    duration_ms=duration_ms,
                    ip_address=request.client.host if request.client else None,
                    error=str(e),
                )
            )
            
            raise
        
        # 计算耗时
        duration_ms = int((time.time() - start_time) * 1000)
        
        # 异步记录操作日志（不阻塞响应）
        if user_id:  # 只记录已认证用户的操作
            asyncio.create_task(
                self._log_operation(
                    user_id=user_id,
                    path=request.url.path,
                    method=request.method,
                    status_code=response.status_code,
                    duration_ms=duration_ms,
                    ip_address=request.client.host if request.client else None,
                )
            )
        
        return response
    
    async def _log_operation(
        self,
        user_id: str | None,
        path: str,
        method: str,
        status_code: int,
        duration_ms: int,
        ip_address: str | None,
        error: str | None = None,
    ):
        """
        记录操作日志到数据库
        
        Args:
            user_id: 用户 ID
            path: 请求路径
            method: HTTP 方法
            status_code: 响应状态码
            duration_ms: 耗时（毫秒）
            ip_address: IP 地址
            error: 错误信息（如果有）
        """
        try:
            # 构建日志详情
            details = {
                "path": path,
                "method": method,
                "status_code": status_code,
                "duration_ms": duration_ms,
            }
            
            if error:
                details["error"] = error
            
            # 敏感路径脱敏
            if path in self.SENSITIVE_PATHS:
                details["path"] = f"{path} [SENSITIVE]"
            
            # 写入数据库
            await self.repo.create({
                "user_id": int(user_id) if user_id and user_id.isdigit() else 0,
                "operation": f"{method} {path}",
                "details": str(details),
                "ip_address": ip_address,
            })
            
            # 记录调试日志
            if duration_ms > 1000:  # 慢请求警告
                logging.warning(
                    f"[Audit] Slow request: {method} {path} "
                    f"({duration_ms}ms, status={status_code})"
                )
            else:
                logging.debug(
                    f"[Audit] {method} {path} "
                    f"({duration_ms}ms, status={status_code})"
                )
        
        except Exception as e:
            # 审计日志失败不应影响主流程
            logging.error(f"[Audit] Failed to log operation: {e}")


def get_user_id_from_request(request: Request) -> str | None:
    """
    从请求中提取用户 ID
    
    Args:
        request: HTTP 请求
        
    Returns:
        用户 ID 或 None
    """
    # 从 request.state 获取（由认证中间件注入）
    return getattr(request.state, "user_id", None)
