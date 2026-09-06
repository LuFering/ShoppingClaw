"""
诊断中间件 - 参考 ScienceClaw 的 DiagnosticMiddleware

在开发模式下记录 LLM 调用的详细信息，包括：
- Prompt 内容
- Response 内容
- Token 消耗
- 耗时统计

仅在 DIAGNOSTIC_MODE=1 时启用。
"""
import logging
import os
import time
from typing import Any, Dict, List

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import StateT
from langgraph.runtime import Runtime
from langgraph.typing import ContextT


class DiagnosticMiddleware(AgentMiddleware):
    """
    诊断中间件
    
    功能:
    1. 记录 LLM 调用的 prompt 和 response
    2. 统计 token 消耗
    3. 测量调用耗时
    4. 仅在生产环境禁用
    
    使用方式:
    ```python
    # 设置环境变量启用诊断模式
    os.environ["DIAGNOSTIC_MODE"] = "1"
    
    middleware = DiagnosticMiddleware()
    graph = builder.compile(middleware=[middleware])
    ```
    """
    
    name = "diagnostic"
    
    def __init__(self):
        self.enabled = os.getenv("DIAGNOSTIC_MODE", "0") == "1"
        self.call_count = 0
        self.total_tokens = 0
        self.total_duration_ms = 0
        
        if self.enabled:
            logging.info("[DiagnosticMiddleware] Enabled (DIAGNOSTIC_MODE=1)")
        else:
            logging.debug("[DiagnosticMiddleware] Disabled (set DIAGNOSTIC_MODE=1 to enable)")
    
    def before_model(self, state: StateT, runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        """模型调用前记录 prompt"""
        if not self.enabled:
            return None
        
        messages = state.get("messages", [])
        if not messages:
            return None
        
        # 记录 prompt 信息
        self.call_count += 1
        start_time = time.time()
        
        # 计算 prompt tokens（简单估算：字符数 / 4）
        prompt_text = "\n".join([str(msg.content) for msg in messages[-5:]])  # 最近 5 条
        prompt_tokens = len(prompt_text) // 4
        
        logging.info(
            f"[Diagnostic] Call #{self.call_count} | "
            f"Prompt tokens: ~{prompt_tokens} | "
            f"Messages: {len(messages)}"
        )
        
        # 保存开始时间到 state
        return {"_diagnostic_start_time": start_time}
    
    def after_model(self, state: StateT, runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        """模型调用后记录 response"""
        if not self.enabled:
            return None
        
        messages = state.get("messages", [])
        if not messages:
            return None
        
        last_msg = messages[-1]
        
        # 获取开始时间
        start_time = state.get("_diagnostic_start_time", time.time())
        duration_ms = int((time.time() - start_time) * 1000)
        
        # 计算 response tokens
        response_text = str(last_msg.content)
        response_tokens = len(response_text) // 4
        
        # 统计总 tokens
        total_tokens = response_tokens
        self.total_tokens += total_tokens
        self.total_duration_ms += duration_ms
        
        # 记录详细信息
        logging.info(
            f"[Diagnostic] Call #{self.call_count} | "
            f"Response tokens: ~{response_tokens} | "
            f"Duration: {duration_ms}ms | "
            f"Avg duration: {self.total_duration_ms // self.call_count}ms"
        )
        
        # 记录响应预览（前 200 字符）
        preview = response_text[:200].replace("\n", " ")
        logging.debug(f"[Diagnostic] Response preview: {preview}...")
        
        # 如果有 usage 信息，记录详细统计
        usage = getattr(last_msg, 'usage_metadata', None)
        if usage:
            logging.info(
                f"[Diagnostic] Token usage: "
                f"prompt={usage.get('input_tokens', 0)}, "
                f"completion={usage.get('output_tokens', 0)}, "
                f"total={usage.get('total_tokens', 0)}"
            )
        
        return None
    
    def get_stats(self) -> dict:
        """获取诊断统计信息"""
        return {
            "enabled": self.enabled,
            "call_count": self.call_count,
            "total_tokens": self.total_tokens,
            "total_duration_ms": self.total_duration_ms,
            "avg_duration_ms": (
                self.total_duration_ms // self.call_count
                if self.call_count > 0
                else 0
            ),
        }
    
    def reset_stats(self):
        """重置统计信息"""
        self.call_count = 0
        self.total_tokens = 0
        self.total_duration_ms = 0
