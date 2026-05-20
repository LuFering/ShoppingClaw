"""
错误映射器 - 参考 ScienceClaw 的 ErrorMapper

将底层技术错误映射为用户友好的中文/英文消息，
避免暴露敏感的技术细节。
"""
import logging
from typing import Any, Dict


class ErrorMapper:
    """
    错误类型映射器
    
    功能:
    1. 分类底层异常
    2. 映射为友好的用户消息
    3. 支持多语言（中文/英文）
    
    使用方式:
    ```python
    mapper = ErrorMapper()
    
    try:
        result = await some_operation()
    except Exception as e:
        error_event = mapper.map(e, lang="zh")
        yield format_sse_event(EventType.ERROR, error_event)
    ```
    """
    
    # 错误类型映射表
    ERROR_MAP: Dict[str, Dict[str, str]] = {
        "context_length_exceeded": {
            "zh": "对话内容过长，已自动裁剪早期内容。如仍有问题，请开启新对话。",
            "en": "Conversation is too long, earlier content has been trimmed. Please start a new chat if the issue persists.",
        },
        "rate_limit_exceeded": {
            "zh": "请求频率过高，请稍后重试。",
            "en": "Rate limit exceeded. Please try again later.",
        },
        "connection_error": {
            "zh": "模型服务暂时不可用，请稍后重试。",
            "en": "Model service is temporarily unavailable. Please try again later.",
        },
        "auth_error": {
            "zh": "认证失败，请检查 API Key 配置。",
            "en": "Authentication failed. Please check your API Key configuration.",
        },
        "timeout": {
            "zh": "请求处理超时，请简化问题后重试。",
            "en": "Request timed out. Please simplify your question and try again.",
        },
        "invalid_request": {
            "zh": "请求参数无效，请检查输入。",
            "en": "Invalid request parameters. Please check your input.",
        },
        "tool_execution_error": {
            "zh": "工具执行失败，请稍后重试。",
            "en": "Tool execution failed. Please try again later.",
        },
        "database_error": {
            "zh": "数据库操作失败，请稍后重试。",
            "en": "Database operation failed. Please try again later.",
        },
        "file_not_found": {
            "zh": "文件不存在，请检查文件路径。",
            "en": "File not found. Please check the file path.",
        },
        "permission_denied": {
            "zh": "权限不足，无法执行此操作。",
            "en": "Permission denied. You don't have permission to perform this action.",
        },
    }
    
    def __init__(self, default_lang: str = "zh"):
        """
        初始化错误映射器
        
        Args:
            default_lang: 默认语言（zh/en）
        """
        self.default_lang = default_lang
    
    def map(self, error: Exception, lang: str | None = None) -> Dict[str, Any]:
        """
        将异常映射为用户友好的错误事件
        
        Args:
            error: 原始异常
            lang: 语言（zh/en），默认使用初始化时设置的语言
            
        Returns:
            结构化的错误事件字典
        """
        if lang is None:
            lang = self.default_lang
        
        # 分类错误类型
        error_type = self._classify(error)
        
        # 获取模板
        template = self.ERROR_MAP.get(error_type, {
            "zh": "处理请求时发生错误，请稍后重试。",
            "en": "An error occurred while processing your request. Please try again later.",
        })
        
        # 构建错误事件
        error_event = {
            "type": "error",
            "error_type": error_type,
            "message": template.get(lang, template["en"]),
            "original_error": str(error) if logging.getLogger().level <= logging.DEBUG else None,
        }
        
        # 记录详细日志（仅开发环境）
        if logging.getLogger().level <= logging.DEBUG:
            logging.error(f"[ErrorMapper] {error_type}: {error}", exc_info=True)
        else:
            logging.warning(f"[ErrorMapper] {error_type}: {template[lang]}")
        
        return error_event
    
    def _classify(self, error: Exception) -> str:
        """
        根据异常类型分类错误
        
        Args:
            error: 原始异常
            
        Returns:
            错误类型字符串
        """
        error_name = type(error).__name__
        error_msg = str(error).lower()
        
        # 上下文长度超限
        if any(keyword in error_msg for keyword in [
            "context_length", "token limit", "maximum context",
            "prompt too long", "input too long"
        ]):
            return "context_length_exceeded"
        
        # 速率限制
        if any(keyword in error_msg for keyword in [
            "rate_limit", "too many requests", "429",
            "throttled", "quota exceeded"
        ]):
            return "rate_limit_exceeded"
        
        # 连接错误
        if isinstance(error, (ConnectionError, TimeoutError)) or any(
            keyword in error_msg for keyword in [
                "connection refused", "connection timeout",
                "network error", "dns resolution",
                "ssl error", "certificate"
            ]
        ):
            return "connection_error"
        
        # 认证错误
        if any(keyword in error_msg for keyword in [
            "authentication", "unauthorized", "401",
            "api key", "invalid token", "forbidden"
        ]):
            return "auth_error"
        
        # 超时
        if isinstance(error, TimeoutError) or any(
            keyword in error_msg for keyword in [
                "timeout", "timed out", "deadline exceeded"
            ]
        ):
            return "timeout"
        
        # 无效请求
        if any(keyword in error_msg for keyword in [
            "invalid parameter", "bad request", "400",
            "validation error", "missing required"
        ]):
            return "invalid_request"
        
        # 工具执行错误
        if any(keyword in error_msg for keyword in [
            "tool execution", "tool call failed",
            "function error", "subagent error"
        ]):
            return "tool_execution_error"
        
        # 数据库错误
        if any(keyword in error_msg for keyword in [
            "database", "sql", "postgres", "mysql",
            "connection pool", "transaction"
        ]):
            return "database_error"
        
        # 文件未找到
        if isinstance(error, FileNotFoundError) or any(
            keyword in error_msg for keyword in [
                "file not found", "no such file", "ENOENT"
            ]
        ):
            return "file_not_found"
        
        # 权限不足
        if any(keyword in error_msg for keyword in [
            "permission denied", "access denied", "403",
            "unauthorized access"
        ]):
            return "permission_denied"
        
        # 默认：未知错误
        return "unknown_error"
    
    def register_custom_error(
        self,
        error_type: str,
        zh_message: str,
        en_message: str,
    ):
        """
        注册自定义错误类型
        
        Args:
            error_type: 错误类型标识
            zh_message: 中文消息
            en_message: 英文消息
        """
        self.ERROR_MAP[error_type] = {
            "zh": zh_message,
            "en": en_message,
        }
        logging.info(f"[ErrorMapper] Registered custom error type: {error_type}")


# 全局单例
_error_mapper: ErrorMapper | None = None


def get_error_mapper() -> ErrorMapper:
    """获取全局 ErrorMapper 实例"""
    global _error_mapper
    if _error_mapper is None:
        _error_mapper = ErrorMapper()
    return _error_mapper
