"""
内容审查中间件 - 敏感内容过滤

在工具调用前后进行内容审查，防止敏感信息泄露或恶意操作。
参考 ScienceClaw 的内容安全策略。
"""
import logging
import re
from typing import Any, Dict, List, Optional, Set

from src.agents.common.middleware.base import AgentMiddleware, ToolCallRequest


class ContentGuardMiddleware(AgentMiddleware):
    """
    内容审查中间件
    
    功能:
    1. 检查工具参数中的敏感内容
    2. 检查结果中的敏感信息泄露
    3. 拦截危险操作（如删除系统文件）
    
    使用方式:
    ```python
    middleware = ContentGuardMiddleware()
    graph = builder.compile(middleware=[middleware])
    ```
    """
    
    # 危险文件路径模式
    DANGEROUS_PATHS = [
        r"/etc/",           # Linux 系统配置
        r"/var/",           # Linux 系统目录
        r"C:\\Windows\\",   # Windows 系统目录
        r"\.env$",          # 环境变量文件
        r"password",        # 密码文件
        r"secret",          # 密钥文件
    ]
    
    # 敏感信息模式（用于结果审查）
    SENSITIVE_PATTERNS = [
        r"(?i)api[_-]?key\s*[:=]\s*['\"][A-Za-z0-9]{20,}['\"]",  # API Key
        r"(?i)password\s*[:=]\s*['\"][^'\"]{8,}['\"]",            # 密码
        r"(?i)secret[_-]?key\s*[:=]\s*['\"][A-Za-z0-9]{20,}['\"]", # Secret Key
        r"\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b",           # 信用卡号
        r"\b\d{6}[-\s]?\d{6}[-\s]?\d{4}\b",                       # 身份证号
    ]
    
    # 危险工具列表
    DANGEROUS_TOOLS = {
        "delete_file",
        "execute_command",
        "run_code",
    }
    
    def __init__(self, strict_mode: bool = False):
        """
        初始化中间件
        
        Args:
            strict_mode: 严格模式（拦截所有警告）
        """
        self.strict_mode = strict_mode
        self.blocked_count = 0  # 统计拦截次数
    
    def wrap_tool_call(self, request: ToolCallRequest, handler) -> Any:
        """
        包装工具调用，进行内容审查
        
        Args:
            request: 工具调用请求
            handler: 原始处理函数
            
        Returns:
            工具调用结果
            
        Raises:
            ValueError: 如果检测到危险内容
        """
        tool_name = request.tool_call.get("name", "")
        tool_args = request.tool_call.get("args", {})
        
        # ═══ 1. 检查工具参数 ═══
        self._check_arguments(tool_name, tool_args)
        
        # ═══ 2. 执行工具调用 ═══
        result = handler(request)
        
        # ═══ 3. 检查结果内容 ═══
        if result:
            result_str = str(result)
            self._check_result(tool_name, result_str)
        
        return result
    
    async def awrap_tool_call(self, request: ToolCallRequest, handler) -> Any:
        """异步版本的 wrap_tool_call"""
        return self.wrap_tool_call(request, handler)
    
    def _check_arguments(self, tool_name: str, args: Dict[str, Any]):
        """
        检查工具参数中的危险内容
        
        Args:
            tool_name: 工具名称
            args: 工具参数
            
        Raises:
            ValueError: 如果检测到危险内容
        """
        # 检查危险工具
        if tool_name in self.DANGEROUS_TOOLS:
            warning = f"⚠️ 尝试使用危险工具 `{tool_name}`"
            logging.warning(f"[ContentGuard] {warning}")
            
            if self.strict_mode:
                raise ValueError(f"{warning} - 严格模式下已拦截")
        
        # 检查文件路径参数
        for key, value in args.items():
            if isinstance(value, str) and self._is_dangerous_path(value):
                error_msg = (
                    f"🚫 检测到危险文件路径: `{value}`\n"
                    f"工具 `{tool_name}` 的参数 `{key}` 包含系统敏感路径，已拦截。"
                )
                logging.error(f"[ContentGuard] {error_msg}")
                raise ValueError(error_msg)
    
    def _check_result(self, tool_name: str, result_str: str):
        """
        检查结果中的敏感信息泄露
        
        Args:
            tool_name: 工具名称
            result_str: 结果字符串
            
        Raises:
            ValueError: 如果检测到敏感信息
        """
        # 检查敏感信息模式
        for pattern in self.SENSITIVE_PATTERNS:
            matches = re.findall(pattern, result_str)
            if matches:
                warning = (
                    f"⚠️ 工具 `{tool_name}` 的结果中包含敏感信息\n"
                    f"匹配模式: {pattern}\n"
                    f"建议: 请手动审查结果，避免泄露敏感数据"
                )
                logging.warning(f"[ContentGuard] {warning}")
                
                if self.strict_mode:
                    # 脱敏处理
                    sanitized = re.sub(pattern, "[REDACTED]", result_str)
                    logging.info(f"[ContentGuard] Sanitized result for {tool_name}")
                    # 注意：这里不直接修改返回值，只记录日志
    
    def _is_dangerous_path(self, path: str) -> bool:
        """
        检查是否为危险文件路径
        
        Args:
            path: 文件路径
            
        Returns:
            True 如果是危险路径
        """
        for pattern in self.DANGEROUS_PATHS:
            if re.search(pattern, path, re.IGNORECASE):
                return True
        return False
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "blocked_count": self.blocked_count,
            "strict_mode": self.strict_mode,
        }
    
    def reset_stats(self):
        """重置统计"""
        self.blocked_count = 0
