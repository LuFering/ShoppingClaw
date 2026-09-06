"""
工具结果卸载中间件 - 参考 ScienceClaw 的 offload_middleware.py

大型工具结果自动写入文件，避免撑爆上下文窗口。
当工具返回结果超过阈值时，将完整结果保存到文件系统，
只返回摘要和文件路径引用给 Agent。
"""
import hashlib
import logging
from typing import Any, Optional

from src.agents.common.middleware.base import AgentMiddleware, ToolCallRequest
from src.agents.common.backends import StateBackend


class ToolResultOffloadMiddleware(AgentMiddleware):
    """
    工具结果卸载中间件
    
    功能:
    1. 检测工具返回结果的大小
    2. 超过阈值时自动写入文件
    3. 返回摘要 + 文件路径引用
    
    使用方式:
    ```python
    backend = FileStateBackend(base_dir="saves/state")
    middleware = ToolResultOffloadMiddleware(backend)
    graph = builder.compile(middleware=[middleware])
    ```
    """
    
    # 普通工具阈值（字符数）
    DEFAULT_THRESHOLD = 3000
    
    # 大文件工具的宽松阈值
    RELAXED_THRESHOLD = 30000
    
    # 哪些工具使用宽松阈值
    RELAXED_TOOLS = {
        "read_file",
        "edit_file", 
        "ls",
        "grep",
        "get_product_full_detail",  # 商品详情可能很大
        "get_products_specs_batch",  # 批量规格
    }
    
    def __init__(self, backend: StateBackend):
        """
        初始化中间件
        
        Args:
            backend: 状态后端（用于写入文件）
        """
        self.backend = backend
        self.offloaded_count = 0  # 统计卸载次数
    
    def wrap_tool_call(self, request: ToolCallRequest, handler) -> Any:
        """
        包装工具调用，检查结果大小并卸载
        
        Args:
            request: 工具调用请求
            handler: 原始处理函数
            
        Returns:
            工具调用结果（可能被替换为摘要）
        """
        # 执行工具调用
        result = handler(request)
        
        # 检查结果大小
        tool_name = request.tool_call.get("name", "")
        result_str = str(result) if result else ""
        
        # 确定阈值
        threshold = (
            self.RELAXED_THRESHOLD
            if tool_name in self.RELAXED_TOOLS
            else self.DEFAULT_THRESHOLD
        )
        
        # 如果结果过大，卸载到文件
        if len(result_str) > threshold:
            return self._offload_result(tool_name, result_str, threshold)
        
        return result
    
    async def awrap_tool_call(self, request: ToolCallRequest, handler) -> Any:
        """异步版本的 wrap_tool_call"""
        return self.wrap_tool_call(request, handler)
    
    def _offload_result(
        self,
        tool_name: str,
        result_str: str,
        threshold: int,
    ) -> str:
        """
        将大型结果卸载到文件
        
        Args:
            tool_name: 工具名称
            result_str: 完整结果字符串
            threshold: 阈值
            
        Returns:
            摘要消息（包含文件路径）
        """
        try:
            # 生成内容哈希（用于文件名）
            content_hash = hashlib.md5(result_str.encode()).hexdigest()[:8]
            
            # 构建文件路径
            file_path = f"research_data/{tool_name}_{content_hash}.txt"
            
            # 写入文件
            self.backend.write(file_path, result_str)
            
            # 更新统计
            self.offloaded_count += 1
            
            # 构建摘要消息
            preview_length = 500
            preview = result_str[:preview_length]
            
            summary = (
                f"⚠️ 工具 `{tool_name}` 返回大量数据 ({len(result_str)} 字符)，"
                f"已自动保存到文件。\n\n"
                f"**文件路径**: `{file_path}`\n\n"
                f"**预览** (前 {preview_length} 字符):\n"
                f"```\n{preview}...\n```\n\n"
                f"💡 **提示**: 使用 `read_file('{file_path}')` 查看完整结果。"
            )
            
            logging.info(
                f"[ToolOffload] Offloaded {tool_name} result "
                f"({len(result_str)} chars → {file_path})"
            )
            
            return summary
            
        except Exception as e:
            logging.error(f"[ToolOffload] Failed to offload result: {e}")
            # 降级：返回截断的结果
            return result_str[:threshold] + f"\n...[结果过长，已截断]"
    
    def get_stats(self) -> dict:
        """获取统计信息"""
        return {
            "offloaded_count": self.offloaded_count,
        }
    
    def reset_stats(self):
        """重置统计"""
        self.offloaded_count = 0
