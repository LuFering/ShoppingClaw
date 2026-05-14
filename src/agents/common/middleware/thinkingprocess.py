from typing import Any

from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import StateT
from langgraph.runtime import Runtime
from langgraph.typing import ContextT
from langgraph.config import get_stream_writer


class ThinkingProcessMiddleware(AgentMiddleware):
    name = "thinking_process"

    def after_model(self, state: StateT, runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        """模型响应后提取推理过程"""
        messages = state.get("messages", [])
        if not messages:
            return None

        last_msg = messages[-1]
        # 如果有 reasoning_content，发送思考步骤
        additional_kwargs = getattr(last_msg, 'additional_kwargs', {})
        reasoning = additional_kwargs.get('reasoning_content') if isinstance(additional_kwargs, dict) else None
        
        if reasoning:
            # 通过 stream_writer 直接发送到前端
            try:
                writer = get_stream_writer()
                writer({
                    "thinking_step": {
                        "type": "thinking",
                        "content": reasoning
                    }
                })
            except Exception:
                pass  # 如果不在流式上下文中，忽略
        
        return None
    
    def after_agent(self, state: StateT, runtime: Runtime[ContextT]) -> dict[str, Any] | None:
        """Agent 执行结束后提取计划步骤和工具调用信息"""
        # 提取 TODO 列表作为计划步骤
        todos = state.get("todos")
        if todos and isinstance(todos, list):
            steps = []
            for i, todo in enumerate(todos[:10]):  # 限制最多 10 个步骤
                if isinstance(todo, dict):
                    steps.append({
                        "id": f"step_{i+1}",
                        "description": todo.get("content", str(todo)),
                        "status": todo.get("status", "pending"),  # pending | running | completed
                        "toolCallIds": todo.get("tool_call_ids", [])
                    })
                else:
                    steps.append({
                        "id": f"step_{i+1}",
                        "description": str(todo),
                        "status": "pending",
                        "toolCallIds": []
                    })
            
            if steps:
                try:
                    writer = get_stream_writer()
                    writer({"plan": {"steps": steps}})
                except Exception:
                    pass
        
        # 提取工具调用历史
        messages = state.get("messages", [])
        tool_calls = []
        for msg in messages:
            msg_type = getattr(msg, 'type', '')
            if msg_type == 'tool':
                tool_calls.append({
                    "tool_call_id": getattr(msg, 'tool_call_id', ''),
                    "name": getattr(msg, 'name', ''),
                    "output": str(getattr(msg, 'content', ''))[:500],
                    "status": "completed"
                })
        
        if tool_calls:
            try:
                writer = get_stream_writer()
                writer({"tool_calls": tool_calls})
            except Exception:
                pass
        
        return None