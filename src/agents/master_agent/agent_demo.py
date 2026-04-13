from pathlib import Path
from typing import Sequence, Callable, Any

from langchain.agents.middleware import AgentMiddleware, InterruptOnConfig
from langchain.agents.structured_output import ResponseFormat
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from langgraph.cache.base import BaseCache
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.types import Checkpointer

from deepagents.backends.protocol import BackendFactory, BackendProtocol
from deepagents.middlleware.subagent import SubAgent, CompiledSubAgent
from src.agents.master_agent.factory import create_agent

BASE_AGENT_PROMPT = (Path(__file__).parent / "BASE_PROMPT.md").read_text(encoding="utf-8")


def create_master_agent(
        model: str | BaseChatModel | None = None,
        tools: Sequence[BaseTool | Callable | dict[str, Any]] | None = None,
        *,
        system_prompt: str | SystemMessage | None = None,
        middleware: Sequence[AgentMiddleware] = (),
        subagents: list[SubAgent | CompiledSubAgent] | None = None,
        skills: list[str] | None = None,
        memory: list[str] | None = None,
        response_format: ResponseFormat | None = None,
        context_schema: type[Any] | None = None,
        checkpointer: Checkpointer | None = None,
        store: BaseStore | None = None,
        backend: BackendProtocol | BackendFactory | None = None,
        interrupt_on: dict[str, bool | InterruptOnConfig] = None,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        debug: bool = False,
        name: str | None = None,
        cache: BaseCache | None = None,
) -> CompiledStateGraph:
    
    # 如果传入的是 None，使用默认模型（从环境变量读取）
    if model is None:
        import os
        ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
        model = ChatOllama(
            model="qwen2.5:3b",
            base_url=ollama_base_url,
        )
    
    if system_prompt is None:
        final_system_prompt = BASE_AGENT_PROMPT
    elif isinstance(system_prompt, SystemMessage):
        existing_text = "\n".join(
            block.get("text", "") 
            for block in system_prompt.content_blocks 
            if isinstance(block, dict) and block.get("type") == "text"
        )
        final_system_prompt = SystemMessage(
            content=f"{existing_text}\n\n{BASE_AGENT_PROMPT}"
        )
    else:
        final_system_prompt = str(system_prompt) + "\n\n" + BASE_AGENT_PROMPT
        
    return create_agent(  # type: ignore[return-value]
        model=model,
        tools=tools,
        system_prompt=final_system_prompt,
        response_format=response_format,
        middleware=middleware,
        context_schema=context_schema,
        checkpointer=checkpointer,
        store=store,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
        debug=debug,
        name=name,
        cache=cache,
    )


def get_main_agent() -> CompiledStateGraph:
    """为 LangGraph Studio 提供的无参数工厂函数"""
    return create_master_agent(
        model="deepseek-r1:1.5b",
    )
