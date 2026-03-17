from pathlib import Path
from typing import Sequence, Callable, Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware, InterruptOnConfig, TodoListMiddleware, HumanInTheLoopMiddleware
from langchain.agents.structured_output import ResponseFormat
from langchain.chat_models import init_chat_model
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.tools import BaseTool
from langchain_ollama import ChatOllama
from langgraph.cache.base import BaseCache
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore
from langgraph.types import Checkpointer

from deepagents.backends.filesystem import FilesystemMiddleware
from deepagents.backends.protocol import BackendProtocol, BackendFactory
from deepagents.backends.state import StateBackend
from deepagents.middlleware.memory import MemoryMiddleware
from deepagents.middlleware.patch_tool_calls import PatchToolCallsMiddleware
from deepagents.middlleware.skills import SkillsMiddleware
from deepagents.middlleware.subagent import SubAgent, CompiledSubAgent, GENERAL_PURPOSE_SUBAGENT, SubAgentMiddleware
from deepagents.middlleware.summarization import _compute_summarization_defaults, DeepAgentsSummarizationMiddleWare

BASE_AGENT_PROMPT = (Path(__file__).parent / "BASE_PROMPT.md").read_text(encoding="utf-8")


def get_default_model():
    """设置默认Model"""
    return ChatOllama(
        model="deepseek-r1:1.5b",
        temperature=0.7,
    )


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
    if model is None:
        model = get_default_model()

        """如果model存在，进行model初始化"""
    elif isinstance(model, str):
        if model.startswith("qwen:"):
            model_init_params: dict = {"temperature": 0.1, "top_p": 0.8}
        else:
            model_init_params = {}

        model = init_chat_model(model,
                                configurable_fields=("model", "temperature"),
                                **model_init_params)

    summarization_defaults = _compute_summarization_defaults(model)

    backend = backend if backend is not None else StateBackend #这里是传StateBackend类名，不是传实例，故不用输入runtime

    gp_middleware: list[AgentMiddleware[Any, Any, Any]] = [ #Generic[Any, Any, Any]类型参数化，让一个基类能适配多种类型组
        TodoListMiddleware(),
        FilesystemMiddleware(backend=backend),
        DeepAgentsSummarizationMiddleWare(
            model=model,
            backend=backend,
            trigger=summarization_defaults,
            keep=summarization_defaults,
            trim_tokens_to_summarize=None,
            truncate_args_settings=summarization_defaults,
        ),
        PatchToolCallsMiddleware(),
    ]
    if skills is not None:
        gp_middleware.append(SkillsMiddleware(backend=backend, sources=skills))
    if interrupt_on is not None:
        gp_middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))

    general_purpose_spec: SubAgent = {
        **GENERAL_PURPOSE_SUBAGENT,
        "model": model,
        "tools": tools or [],
        "middleware": gp_middleware,
    }
    # 往上是对主agent
    # 往下是对子agent
    processed_subagents: list[SubAgent | CompiledSubAgent] = []
    for spec in subagents or []:
        if "runnable" in spec:
            processed_subagents.append(spec)
        else:
            subagent_model = spec.get("model", model)
            if isinstance(subagent_model, str):
                subagent_model = init_chat_model(subagent_model)

            subagent_summarization_defaults = _compute_summarization_defaults(subagent_model)
            subagent_middleware: list[AgentMiddleware[Any, Any, Any]] = [
                TodoListMiddleware(),
                FilesystemMiddleware(backend=backend),
                DeepAgentsSummarizationMiddleWare(
                    model=subagent_model,
                    backend=backend,
                    trigger=subagent_summarization_defaults,
                    keep=subagent_summarization_defaults,
                    trim_tokens_to_summarize=None,
                    truncate_args_settings=subagent_summarization_defaults,
                ),
                PatchToolCallsMiddleware(),
            ]
            subagent_skills = spec.get("skills")
            if subagent_skills:
                subagent_middleware.append(SkillsMiddleware(backend=backend, sources=subagent_skills))
            subagent_middleware.extend(spec.get("middleware", []))

            processed_spec: SubAgent = {
                **spec,
                "model": subagent_model,
                "tools": spec.get("tools", tools or []),
                "middleware": subagent_middleware,
            }

            processed_subagents.append(processed_spec)

    all_subagents: list[SubAgent | CompiledSubAgent] = [general_purpose_spec, *processed_subagents]

    mainagent_middleware: list[AgentMiddleware[Any, Any, Any]] = [
        TodoListMiddleware(),
    ]
    if memory is not None:
        mainagent_middleware.append(MemoryMiddleware(backend=backend, sources=memory))
    if skills is not None:
        mainagent_middleware.append(SkillsMiddleware(backend=backend, sources=skills))
    mainagent_middleware.extend(
        [
            FilesystemMiddleware(backend=backend),
            SubAgentMiddleware(
                backend=backend,
                subagents=all_subagents,
            ),
            DeepAgentsSummarizationMiddleWare(
                model=model,
                backend=backend,
                trigger=summarization_defaults,
                keep=summarization_defaults,
                trim_tokens_to_summarize=None,
                truncate_args_settings=summarization_defaults,
            ),
            PatchToolCallsMiddleware(),
        ]
    )
    if middleware:
        mainagent_middleware.extend(middleware)
    if interrupt_on is not None:
        mainagent_middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))

    if system_prompt is None:
        final_system_prompt: str | SystemMessage | BASE_AGENT_PROMPT
    elif isinstance(system_prompt, SystemMessage):
        final_system_prompt = SystemMessage(
            content_blocks=[*system_prompt.content_blocks, {"type": "text", "text": f"\n\n{BASE_AGENT_PROMPT}"}])
    else:
        final_system_prompt = system_prompt + "\n\n" + BASE_AGENT_PROMPT

    return create_agent(
        model,
        system_prompt=final_system_prompt,
        tools=tools,
        middleware=mainagent_middleware,
        response_format=response_format,
        context_schema=context_schema,
        checkpointer=checkpointer,
        store=store,
        debug=debug,
        name=name,
        cache=cache,
    ).with_config({"recursion_limit":1000})
