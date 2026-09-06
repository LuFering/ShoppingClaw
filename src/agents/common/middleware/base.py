"""Middleware base classes and types.

Re-exports AgentMiddleware from langchain and defines ToolCallRequest
for type-safe tool call interception in custom middleware.
"""

from typing import Any, Protocol, runtime_checkable

from langchain.agents.middleware import AgentMiddleware


@runtime_checkable
class ToolCallRequest(Protocol):
    """Protocol for tool call request objects passed to wrap_tool_call.

    Compatible with LangGraph's internal ToolCallRequest structure.
    """

    tool_call: dict[str, Any]


__all__ = ["AgentMiddleware", "ToolCallRequest"]
