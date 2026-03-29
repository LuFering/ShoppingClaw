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
from src.agents.graph import create_agent

BASE_AGENT_PROMPT = (Path(__file__).parent / "BASE_PROMPT.md").read_text(encoding="utf-8")


def create_main_agent(
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
        debug: bool = False,
        name: str | None = None,
        cache: BaseCache | None = None,
) -> CompiledStateGraph:
    # 如果传入的是字符串，创建 ChatOllama 实例
    if isinstance(model, str):
        model = ChatOllama(
            model=model,
            base_url="http://localhost:11434",  # 硬编码地址，不依赖环境变量
        )
    # 如果传入的是 None，使用默认模型
    elif model is None:
        model = ChatOllama(
            model="qwen2.5:3b",
            base_url="http://localhost:11434",  # 硬编码地址，不依赖环境变量
        )
    if system_prompt is None:
        final_system_prompt = BASE_AGENT_PROMPT
    elif isinstance(system_prompt, SystemMessage):
        # 合并 content_blocks 中的文本
        existing_text = "\n".join(
            block.get("text", "") 
            for block in system_prompt.content_blocks 
            if isinstance(block, dict) and block.get("type") == "text"
        )
        final_system_prompt = SystemMessage(
            content=f"{existing_text}\n\n{BASE_AGENT_PROMPT}"
        )
    else:
        final_system_prompt = system_prompt + "\n\n" + BASE_AGENT_PROMPT
    # 如果传入的是 BaseChatModel 子类实例，直接使用
    return create_agent(  # type: ignore[return-value]
        model,
        system_prompt=final_system_prompt,
    )


def get_main_agent() -> CompiledStateGraph:
    """为 LangGraph Studio 提供的无参数工厂函数"""
    return create_main_agent(
        model="deepseek-r1:1.5b",
    )
