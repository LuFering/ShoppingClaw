import logging
import re
from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import StateT
from langgraph.runtime import Runtime
from langgraph.typing import ContextT
from langgraph.config import get_stream_writer

# 思考内容最大字符数，超过则截断
MAX_THINKING_CHARS = 500
# 截断标记
TRUNCATION_MARKER = "\n...(思考过程已截断)"


class ThinkingProcessMiddleware(AgentMiddleware):
    name = "thinking_process"

    def __init__(self, max_thinking_chars: int = MAX_THINKING_CHARS):
        super().__init__()
        self._max_chars = max_thinking_chars

    def after_model(self, state: StateT, runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        """模型响应后提取推理过程"""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        additional_kwargs = getattr(last_msg, 'additional_kwargs', {})
        response_metadata = getattr(last_msg, 'response_metadata', {})

        reasoning = (
            additional_kwargs.get('reasoning_content') or
            response_metadata.get('reasoning_content') or
            ''
        )

        tool_calls = getattr(last_msg, 'tool_calls', None)
        has_tool_calls = bool(tool_calls)

        if reasoning:
            original_len = len(reasoning)
            was_truncated = False

            # 超长截断
            if len(reasoning) > self._max_chars:
                reasoning = reasoning[:self._max_chars] + TRUNCATION_MARKER
                was_truncated = True
                logging.warning(
                    f"[ThinkingMiddleware] 思考内容超长截断: {original_len} -> {len(reasoning)} 字符"
                )

            # 检测末尾完整性：以乱码/不完整英文/未闭合标点结尾
            if self._is_truncated(reasoning):
                if not was_truncated:
                    reasoning = reasoning[:self._max_chars] + TRUNCATION_MARKER
                    was_truncated = True
                logging.warning(
                    f"[ThinkingMiddleware] 检测到思考内容末尾不完整，已添加截断标记"
                )

            try:
                writer = get_stream_writer()
                logging.info(
                    f"[ThinkingMiddleware] 发送 reasoning_content "
                    f"(原始:{original_len}, 发送:{len(reasoning)}, "
                    f"截断:{was_truncated}, 工具调用:{has_tool_calls})"
                )
                writer({
                    "status": "thinking_process",
                    "event": "thinking",
                    "content": reasoning
                })
            except Exception as e:
                logging.warning(f"[ThinkingMiddleware] 写入 stream_writer 失败: {e}")
        else:
            logging.info(
                f"[ThinkingMiddleware] 未找到 reasoning_content, "
                f"additional_kwargs keys: {list(additional_kwargs.keys()) if isinstance(additional_kwargs, dict) else 'N/A'}"
            )

        # 若模型生成了工具调用，路由到 tools 节点执行（替代原 GapDetector 的跳转逻辑）
        if has_tool_calls:
            return {"jump_to": "tools"}

        return None

    @staticmethod
    def _is_truncated(content: str) -> bool:
        """检测思考内容末尾是否不完整（被API截断）"""
        if not content or len(content) < 30:
            return False

        last_50 = content[-50:] if len(content) >= 50 else content

        # 中文末字是否为不完整的 UTF-8 代理对或控制字符
        if '�' in last_50:
            return True

        # 末尾是否以不完整的英文单词结尾（如 "theirbudgetrang" 连在一起）
        # 1. 连续的小写英文字母 > 20 且无空格分隔
        garbled_english = re.search(r'[a-z]{20,}$', last_50)
        if garbled_english:
            return True

        # 2. 中英混用 + 无明显标点结束，且末尾是英文字母
        has_chinese = bool(re.search(r'[一-鿿]', last_50))
        if has_chinese:
            # 中文后紧跟未完成的英文片段
            tail = re.search(r'[一-鿿][a-z\s]{5,}$', last_50)
            if tail:
                return True

        return False
    
    def after_agent(self, state: StateT, runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        """Agent 执行结束后提取计划步骤和工具调用信息"""
        # 提取 TODO 列表作为计划步骤
        todos = state.get("todos")
        if todos and isinstance(todos, list):
            steps = []
            for i, todo in enumerate(todos[:10]):  # 限制最多 10 个步骤
                if isinstance(todo, dict):
                    steps.append({
                        "id": str(todo.get("id") or f"step_{i+1}"),
                        "description": todo.get("content", str(todo)),
                        "title": todo.get("content", str(todo)),
                        "status": self._normalize_status(todo.get("status", "pending")),
                        "toolCallIds": todo.get("tool_call_ids", [])
                    })
                else:
                    steps.append({
                        "id": f"step_{i+1}",
                        "description": str(todo),
                        "title": str(todo),
                        "status": "pending",
                        "toolCallIds": []
                    })
            
            if steps:
                try:
                    writer = get_stream_writer()
                    # 使用新 SSE 协议格式
                    writer({
                        "status": "thinking_process",
                        "event": "plan_update",
                        "plan": {"steps": steps}
                    })
                except Exception:
                    pass
        
        return None
    
    def _normalize_status(self, status: str | None) -> str:
        """标准化步骤状态"""
        value = (status or "pending").lower()
        if value in {"completed", "complete", "done", "success"}:
            return "completed"
        if value in {"in_progress", "running", "active", "processing"}:
            return "running"
        if value in {"failed", "error", "cancelled", "canceled"}:
            return "failed"
        return "pending"