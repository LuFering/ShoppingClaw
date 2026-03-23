import itertools
from typing import Sequence, Any, Callable

from aiohttp.web_middlewares import middleware
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware
from langchain.agents.middleware.types import StateT_co, ResponseT
from langchain.agents.structured_output import OutputToolBinding, ResponseFormat
from langchain_core.language_models import BaseChatModel
from langchain_core.tools import BaseTool
from langgraph._internal._runnable import RunnableCallable
from langgraph.cache.base import BaseCache
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore
from langgraph.types import Command, Checkpointer
from langgraph.typing import ContextT


def model_node(
        state: AgentState[Any],
        runtime: Runtime[ContextT]
) -> list[Command[Any]]:
    """定义model_node"""
    pass


async def amodel_node(
        state: AgentState[Any],
        runtime: Runtime[ContextT]
) -> list[Command[Any]]:
    """model_node的异步函数"""
    pass


def _get_real_middleware_list(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]]
) -> (list, list, list, list):
    """hook函数列表"""
    before_agent = [
        m for m in middleware
        if m.__class__.before_agent is not AgentMiddleware.before_agent
           or m.__class__.abefore_agent is not AgentMiddleware.abefore_agent
    ]
    before_model = [
        m for m in middleware
        if m.__class__.before_model is not AgentMiddleware.before_model
           or m.__class__.abefore_model is not AgentMiddleware.abefore_model
    ]
    after_agent = [
        m for m in middleware
        if m.__class__.after_agent is not AgentMiddleware.after_agent
           or m.__class__.aafter_agent is not AgentMiddleware.aafter_agent
    ]
    after_model = [
        m for m in middleware
        if m.__class__.after_model is not AgentMiddleware.after_model
           or m.__class__.aafter_model is not AgentMiddleware.aafter_model
    ]

    return (before_agent, before_model,
            after_model, after_agent)


def _get_entry_node(
        before_agent: Sequence[AgentMiddleware[StateT_co, ContextT]],
        before_model: Sequence[AgentMiddleware[StateT_co, ContextT]],
) -> str:
    """entry_node节点判断"""
    if before_agent:
        entry_node = f"{before_agent[0].name}.before_agent"
    elif before_model:
        entry_node = f"{before_model[0].name}.before_model"
    else:
        entry_node = "model"

    return entry_node


def _get_loop_entry_node(
        before_model: Sequence[AgentMiddleware[StateT_co, ContextT]],
) -> str:
    """loop循环entry节点判断"""
    if before_model:
        loop_entry_node = f"{before_model[0].name}.before_model"
    else:
        loop_entry_node = "model"

    return loop_entry_node


def _get_loop_exit_node(
        after_model: Sequence[AgentMiddleware[StateT_co, ContextT]],
) -> str:
    """loop循环exit节点判断"""
    if after_model:
        loop_exit_node = f"{after_model[0].name}.after_model"
    else:
        loop_exit_node = "model"

    return loop_exit_node


def _get_exit_node(
        after_agent: Sequence[AgentMiddleware[StateT_co, ContextT]],
) -> str:
    """exit节点判断"""
    if after_agent:
        exit_node = f"{after_agent[0].name}.after_agent"
    else:
        exit_node = END

    return exit_node


def _chain_tool_call(wrapper: list):
    pass


def _get_tool_call(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
):
    middleware_tool_call = [
        m for m in middleware
        if m.__class__.wrap_tool_call is not AgentMiddleware.wrap_tool_call
           or m.__class__.awrap_tool_call is not AgentMiddleware.awrap_tool_call
    ]
    if middleware_tool_call:
        wrapper = [
            m.wrap_tool_call
            for m in middleware_tool_call
        ]
        wrap_tool_call_wrapper = _chain_tool_call(wrapper)

    return wrap_tool_call_wrapper


def _chain_async_tool_call(async_wrapper: list):
    pass


def _get_async_tool_call(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
):
    middleware_async_tool_call = [
        m for m in middleware
        if m.__class__.wrap_tool_call is not AgentMiddleware.wrap_tool_call
           or m.__class__.awrap_tool_call is not AgentMiddleware.awrap_tool_call
    ]
    async_wrap_tool_call_wrapper = None
    if middleware_async_tool_call:
        async_wrapper = [
            m.awrap_tool_call
            for m in middleware_async_tool_call
        ]
        async_wrap_tool_call_wrapper = _chain_async_tool_call(async_wrapper)

    return async_wrap_tool_call_wrapper


def _get_tools(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
        tools: Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | None,
) -> (list, list, list, list):
    middleware_tools = [t for m in middleware for t in getattr(m, "tools", [])]  # 从middleware取出tools属性，其是个list
    llm_tools = [t for t in tools if isinstance(t, dict)]
    external_tools = [t for t in tools if not isinstance(t, dict)]
    available_tools = middleware_tools + external_tools

    return (middleware_tools, llm_tools,
            external_tools, available_tools)


def __merged_schema():
    pass


def _get_schema(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]]
):
    state_schemas: set[type] = {m.state_schema for m in middleware}
    merged_state_schema = __merged_schema()  # 合并所有state_schema
    input_schema = __merged_schema()  # 挑出输入
    output_schema = __merged_schema()  # 挑出输出

    return (state_schemas, merged_state_schema,
            input_schema, output_schema)


def create_agent(
        model: str | BaseChatModel,
        tools: Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | None = None,
        *,
        response_format: ResponseFormat[ResponseT] | type[ResponseT] | dict[str, Any] | None = None,
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]] = (),
        # StateT_co是协变变量，如果 A 是 B 的子类，那么 Container[A] 也是 Container[B] 的子类
        context_schema: type[ContextT] | None = None,  # 要的是能产出ContextT对象的类
        checkpointer: Checkpointer | None = None,
        store: BaseStore | None = None,
        interrupt_before: list[str] | None = None,
        interrupt_after: list[str] | None = None,
        debug: bool = False,
        name: str | None = None,
        cache: BaseCache[Any] | None = None,
) -> CompiledStateGraph:
    """工作流搭建"""
    """四大中间件列表[hook]"""
    (middleware_before_agent, middleware_before_model,
     middleware_after_model, middleware_after_agent) = _get_real_middleware_list(middleware)

    """entry_node"""
    entry_node = _get_entry_node(middleware_before_agent, middleware_before_model)

    """exit_node"""
    exit_node = _get_exit_node(middleware_after_agent)

    """loop_entry_node"""
    loop_entry_node = _get_loop_entry_node(middleware_before_model)

    """loop_exit_node"""
    loop_exit_node = _get_loop_exit_node(middleware_after_model)

    structured_output_tools: dict[str, OutputToolBinding[Any]] = {}

    """wrap_tool_call_wrapper"""
    wrap_tool_call_wrapper = _get_tool_call(middleware)

    """async_wrap_tool_call_wrapper"""
    async_wrap_tool_call_wrapper = _get_async_tool_call(middleware)

    """tools列表"""
    (middleware_tools, llm_tools,
     external_tools, available_tools) = _get_tools(middleware, tools)

    """创建tool_node节点"""
    tool_node: ToolNode | None = None
    tool_node = (
        ToolNode(
            tools=available_tools,
            wrap_tool_call=wrap_tool_call_wrapper,
            awrap_tool_call=async_wrap_tool_call_wrapper,
        ))

    """tool节点之后的节点方向"""
    tools_to_model_destinations = [loop_entry_node]
    if (
            any(tool.return_direct for tool in tool_node.tools_by_name.values())
            or structured_output_tools
    ):
        tools_to_model_destinations.append(exit_node)

    """model节点之后的节点方向"""
    model_to_tools_destinations = ["tools", exit_node]
    if response_format or loop_exit_node != "model":
        model_to_tools_destinations.append(loop_entry_node)

    """四大schema"""
    (state_schemas, merged_state_schema,
     input_schema, output_schema) = _get_schema(middleware)

    """建graph"""
    graph: StateGraph[] = StateGraph(
        State_schema=merged_state_schema,
        input_schema=input_schema,
        output_schema=output_schema,
        context_schema=context_schema,
    )

    """添加model节点"""
    graph.add_node("model", RunnableCallable(model_node, amodel_node))

    """添加tools节点"""
    graph.add_node("tools", tool_node)

    """添加middleware节点"""
    for m in middleware:
        if (
                m.__class__.before_agent is not AgentMiddleware.before_agent
                or m.__class__.before_agent is not AgentMiddleware.before_agent
        ):
            sync_before_agent = (
                m.before_agent
                if m.__class__.before_agent is not AgentMiddleware.before_agent
                else None
            )
            async_before_agent = (
                m.abefore_agent
                if m.__class__.abefore_agent is not AgentMiddleware.abefore_agent
                else None
            )
            before_agent_node = RunnableCallable(sync_before_agent, async_before_agent)
            graph.add_node(
                f"{m.name}.before_agent",
                before_agent_node,
                input_schema=merged_state_schema
            )

        if (
                m.__class__.before_model is not AgentMiddleware.before_model
                or m.__class__.abefore_model is not AgentMiddleware.abefore_model
        ):
            sync_before_model = (
                m.before_model
                if m.__class__.before_model is not AgentMiddleware.before_model
                else None
            )
            async_before_model = (
                m.abefore_model
                if m.__class__.abefore_model is not AgentMiddleware.abefore_model
                else None
            )
            before_model_node = RunnableCallable(sync_before_model, async_before_model)
            graph.add_node(
                f"{m.name}.before_model",
                before_model_node,
                input_schema=merged_state_schema
            )

    """构建从Start到entry_node的edge"""
    graph.add_edge(START, entry_node)

    """构建从tools到model的条件边"""
    graph.add_conditional_edges(
        "tools",
        RunnableCallable(  # 路由函数
            _choose_tools_model_edge(
                tool_node=tool_node,
                model_destinations=loop_entry_node,
                structured_output_tools=structured_output_tools,
                end_destination=exit_node,
            ),
            trace=False
        ),
        tools_to_model_destinations,  # 目标节点列表
    )

    """构建从model到出点的条件边"""
    graph.add_conditional_edges(
        loop_exit_node,
        RunnableCallable(
            _choose_model_to_tools_edge(
                model_destinations=loop_entry_node,
                structured_output_tools=structured_output_tools,
                end_destination=exit_node
            ),
            trace=False,
        ),
        tools_to_model_destinations,
    )

    """构建before_agent middleware 边"""
    for m1, m2 in itertools.pairwise(middleware_before_agent):  # 输入[A, B, C, D]，会输出(A, B), (B, C), (C, D)
        _add_middleware_edge(  # 两两连接中间件node
            graph,
            name=f"{m1.name}.before_agent",
            default_destination=f"{m2.name}.before_agent",
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_to_jump_to(m1, "before_agent"),
        )
    _add_middleware_edge(  # 将最后一个middleware node和loop_entry_node连接
        graph,
        name=f"{middleware_before_agent[-1].name}.before_agent",
        default_destination=loop_entry_node,
        model_destination=loop_entry_node,
        end_destination=exit_node,
        can_jump_to=_get_can_to_jump_to(middleware_before_agent[-1], "before_agent"),
    )

    """构建before_model middleware 边"""
    for m1, m2 in itertools.pairwise(middleware_before_model):
        _add_middleware_edge(
            graph,
            name=f"{m1.name}.before_model",
            default_destinantion=f"{m2.name}.before_model",
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_to_jump_to(m1, "before_model"),
        )
    _add_middleware_edge(
        graph,
        name=f"{middleware_before_model[-1].name}.before_model",
        default_destination="model",
        model_destination=loop_entry_node,
        end_destination=exit_node,
        can_jump_to=_get_can_to_jump_to(middleware_before_model[-1], "before_model"),
    )

    """构建after_model middleware 边"""
    for idx in range(len(middleware_after_model) - 1, 0, -1):  # 手写倒序，输入[A,B,C],输出[C,B],[B,A]
        m1 = middleware_after_model[idx]
        m2 = middleware_after_model[idx - 1]
        _add_middleware_edge(
            graph,
            name=f"{m1.name}.after_model",
            default_destination=f"{m2.name}.after_model",
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_to_jump_to(m1, "after_model"),
        )
    # Model节点不具备重新回到model节点和直接退出的功能，否则过于冗余
    graph.add_edge("model", f"{middleware_after_model[-1].name}.after_model")

    """构建after_agent middleware 边"""
    for idx in range(len(middleware_after_agent) - 1, 0, -1):
        m1 = middleware_after_agent[idx]
        m2 = middleware_after_agent[idx - 1]
        _add_middleware_edge(
            graph,
            name=f"{m1.name}.after_agent",
            default_destination=f"{m2.name}.after_agent",
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_to_jump_to(m1, "after_agent"),
        )
    _add_middleware_edge(
        graph,
        name=f"{middleware_after_agent[0].name}.after_agent",
        default_destiantion=END,
        model_destination=loop_entry_node,
        end_destination=exit_node,
        can_jump_to=_get_can_to_jump_to(middleware_after_agent[0], "after_agent"),
    )

    return graph.compile(
        checkpointer=checkpointer,
        store=store,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
        debug=debug,
        name=name,
        cache=cache,
    ).with_config(config)
