import itertools
from dataclasses import field, dataclass
from typing import Sequence, Any, Callable, Awaitable, Generic, get_type_hints, Required, NotRequired, get_args, \
    Annotated

from aiohttp.web_middlewares import middleware
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, ModelResponse, ExtendedModelResponse
from langchain.agents.middleware.types import StateT_co, ResponseT, ModelRequest, OmitFromSchema
from langchain.agents.structured_output import OutputToolBinding, ResponseFormat, ToolStrategy, ProviderStrategy, \
    AutoStrategy
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage, AIMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langgraph._internal._runnable import RunnableCallable
from langgraph.cache.base import BaseCache
from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import ToolNode
from langgraph.prebuilt.tool_node import ToolCallWrapper, ToolCallRequest
from langgraph.runtime import Runtime
from langgraph.store.base import BaseStore
from langgraph.types import Command, Checkpointer
from langgraph.typing import ContextT, NodeInputT
from mypyc.irbuild.util import TypedDict
from typing_extensions import get_origin


@dataclass  # 类似java的@data,自动创建__init__构造函数
class _ComposedExtendedModelResponse(Generic[ResponseT]):
    model_response: ModelResponse[ResponseT]
    commands: list[Command[Any]] = field(default_factory=list)  # field(default_factory)会在每次实例类时调用list函数创建list


def model_node(
        model: str | BaseChatModel,
        tools: Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] | None,
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
        initial_response_format: ToolStrategy[Any] | ProviderStrategy[Any] | AutoStrategy[Any] | None,
        state: AgentState[Any],
        runtime: Runtime[ContextT],
) -> list[Command[Any]]:
    """定义model_node"""
    default_tools = []
    request = ModelRequest(  # 发送给LLM的标准数据包
        model=model,
        tools=default_tools,
        response_format=initial_response_format,
        messages=state["messages"],
        tool_choice=None,
        state=state,
        runtime=runtime
    )

    if _get_model_call(middleware) is None:


def _execute_model_sync(
        request: ModelRequest,
) -> ModelResponse:
    BaseChatModel, effective_response_format = _get_bound_model(request)


def _get_bound_model(
        request: ModelRequest,
) -> tuple[Runnable[Any, Any], ResponseFormat[Any] | None]:
    pass


async def amodel_node(
        state: AgentState[Any],
        runtime: Runtime[ContextT]
) -> list[Command[Any]]:
    """model_node的异步函数"""
    pass


def _get_real_middleware_list(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
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
        exit_node = f"{after_agent[-1].name}.after_agent"
    else:
        exit_node = END

    return exit_node


def _chain_tool_call(
        wrappers: Sequence[ToolCallWrapper]
) -> ToolCallWrapper | None:
    def compose_two(outer: ToolCallWrapper, inner: ToolCallWrapper) -> ToolCallWrapper:
        """
        将两个 wrapper 组合成一个新的 wrapper（outer 包裹 inner）。
        :param outer:外层 wrapper（先执行）
        :param inner:内层 wrapper（后执行）
        :return:一个新的 wrapper，行为等价于 outer(inner(execute))

        执行顺序：
        请求流： outer -> inner -> execute
        返回流： execute -> inner -> outer
        """

        def composed(
                request: ToolCallRequest,
                execute: Callable[[ToolCallRequest], ToolMessage | Command[Any]],
        ) -> ToolMessage | Command[Any]:
            """outer不直接调用execute,而是调用call_inner，实现wrapper中间件层层包裹"""

            def call_inner(request: ToolCallRequest) -> ToolMessage | Command[Any]:
                return inner(request, execute)  # 调用execute的真正中间件

            return outer(request, call_inner)

        return composed

    result = wrappers[-1]  # [A,B,C],取出的是C
    for wrapper in reversed(wrappers[:-1]):  # =>[B,A]
        result = compose_two(wrapper, result)
    return result


def _chain_async_tool_call(
        async_wrappers: Sequence[
            Callable[
                [ToolCallRequest, Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]]],
                Awaitable[ToolMessage | Command[Any]],
            ]
        ],
) -> (
        Callable[
            [ToolCallRequest, Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]]],
            Awaitable[ToolMessage | Command[Any]],
        ]
        | None
):
    """参数类似于async def wrapper(
                    request: ToolCallRequest,
                    execute: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command]]
                    ) -> ToolMessage | Command:
                    ..."""

    def compose_two(
            outer: Callable[
                [ToolCallRequest, Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]]],
                Awaitable[ToolMessage | Command[Any]],
            ],
            inner: Callable[
                [ToolCallRequest, Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]]],
                Awaitable[ToolMessage | Command[Any]],
            ],
    ) -> Callable[
        [ToolCallRequest, Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]]],
        Awaitable[ToolMessage | Command[Any]],
    ]:
        async def composed(
                request: ToolCallRequest,
                execute: Callable[[ToolCallRequest], Awaitable[ToolMessage | Command[Any]]],
        ) -> ToolMessage | Command[Any]:
            async def call_inner(req: ToolCallRequest) -> ToolMessage | Command[Any]:
                return await inner(req, execute)

            return await inner(request, call_inner)

        return composed

    result = async_wrappers[-1]
    for async_wrapper in reversed(async_wrappers[:-1]):
        result = compose_two(async_wrapper, result)

    return result


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
    # wrap_tool_call_wrapper 是包裹tool的wrapper层，用于在tool执行的前，中，后阶段，对调用过程进行控制，增强或拦截等操作
    return wrap_tool_call_wrapper


def _normalize_to_model_response(
        result: ModelResponse | AIMessage | ExtendedModelResponse,
) -> ModelResponse:
    """从result中提取model_response"""
    if isinstance(result, AIMessage):
        return ModelResponse(result=[result], structured_response=None)
    if isinstance(result, ExtendedModelResponse):
        return result.model_response
    else:
        return result


def _chain_model_call(
        sync_handlers: Sequence[
            Callable[
                [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], ModelResponse]],
                ModelResponse | AIMessage | ExtendedModelResponse,
            ]
        ],
) -> Callable[
    [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], ModelResponse]],
    _ComposedExtendedModelResponse,
]:
    """将model_call_handler进行链接"""

    def _to_composed_result(
            result: ModelResponse | AIMessage | ExtendedModelResponse | _ComposedExtendedModelResponse,
            extra_commands: list[Command[Any]] | None = None,
    ) -> _ComposedExtendedModelResponse:
        """为result统一格式"""
        commands: list[Command[Any]] = list(extra_commands or [])  # 如果 extra_commands 存在 → 复制一份,如果没有 → 空列表 []
        if isinstance(result, _ComposedExtendedModelResponse):  # 有commands
            commands.extend(result.commands)
            model_response = result.model_response
        elif isinstance(result, ExtendedModelResponse):  # 可能有commands，可能是没有
            model_response = result.model_response
            if result.command is not None:
                commands.append(result.command)
        else:
            model_response = _normalize_to_model_response(result)
        return _ComposedExtendedModelResponse(model_response=model_response, commands=commands)  # 创建统一实例

    def composed_two(
            outer: Callable[
                       [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], ModelResponse]],
                       ModelResponse | AIMessage | ExtendedModelResponse
                   ]
                   | Callable[
                       [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], ModelResponse]],
                       _ComposedExtendedModelResponse
                   ],
            inner: Callable[
                       [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], ModelResponse]],
                       ModelResponse | AIMessage | ExtendedModelResponse
                   ]
                   | Callable[
                       [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], ModelResponse]],
                       _ComposedExtendedModelResponse
                   ],
    ) -> Callable[
        [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], ModelResponse]],
        _ComposedExtendedModelResponse
    ]:
        def composed(
                request: ModelRequest[ContextT],
                handler: Callable[[ModelRequest[ContextT]], ModelResponse],
        ) -> _ComposedExtendedModelResponse:
            accumulated_commands: list[Command[Any]] = []  # command累加

            def inner_handle(req: ModelRequest[ContextT]) -> ModelResponse:
                accumulated_commands.clear()
                inner_result = inner(req, handler)  # 执行handler的真正函数
                if isinstance(inner_result, _ComposedExtendedModelResponse):
                    accumulated_commands.extend(inner_result.commands)
                    return inner_result.model_response
                if isinstance(inner_result, ExtendedModelResponse):
                    if inner_result.command is not None:
                        accumulated_commands.append(inner_result.command)
                    return inner_result.model_response
                return _normalize_to_model_response(inner_result)

            outer_result = outer(request, inner_handle)
            return _to_composed_result(
                outer_result,
                extra_commands=accumulated_commands,
            )

        return composed

    composed_handler = composed_two(sync_handlers[-2], sync_handlers[-1])  # 列表最后一个和最后第二个进行链接
    for h in reversed(sync_handlers[:-2]):
        composed_handler = composed_two(h, composed_handler)
    return composed_handler


def _chain_async_model_call(
        async_handlers: Sequence[
            Callable[
                [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse]]],
                Awaitable[ModelResponse | AIMessage | ExtendedModelResponse],
            ]
        ],
) -> Callable[
    [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse]]],
    Awaitable[_ComposedExtendedModelResponse],
]:
    def _to_composed_result(
            result: ModelResponse | AIMessage | ExtendedModelResponse | _ComposedExtendedModelResponse,
            extra_commands: list[Command[Any]] | None = None,
    ) -> _ComposedExtendedModelResponse:
        """为result统一格式"""
        commands: list[Command[Any]] = list(extra_commands or [])  # 如果 extra_commands 存在 → 复制一份,如果没有 → 空列表 []
        if isinstance(result, _ComposedExtendedModelResponse):  # 有commands
            commands.extend(result.commands)
            model_response = result.model_response
        elif isinstance(result, ExtendedModelResponse):  # 可能有commands，可能是没有
            model_response = result.model_response
            if result.command is not None:
                commands.append(result.command)
        else:
            model_response = _normalize_to_model_response(result)
        return _ComposedExtendedModelResponse(model_response=model_response, commands=commands)  # 创建统一实例

    def composed_two(
            outer: Callable[
                       [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse]]],
                       Awaitable[ModelResponse | AIMessage | ExtendedModelResponse]
                   ]
                   | Callable[
                       [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse]]],
                       Awaitable[_ComposedExtendedModelResponse]
                   ],
            inner: Callable[
                       [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse]]],
                       Awaitable[ModelResponse | AIMessage | ExtendedModelResponse]
                   ]
                   | Callable[
                       [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse]]],
                       Awaitable[_ComposedExtendedModelResponse]
                   ],
    ) -> Callable[
        [ModelRequest[ContextT], Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse]]],
        Awaitable[_ComposedExtendedModelResponse]
    ]:
        async def composed(
                request: ModelRequest[ContextT],
                handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse]],
        ) -> _ComposedExtendedModelResponse:
            accumulated_commands: list[Command[Any]] = []  # command累加

            async def inner_handle(req: ModelRequest[ContextT]) -> ModelResponse:
                accumulated_commands.clear()
                inner_result = await inner(req, handler)  # 执行handler的真正函数
                if isinstance(inner_result, _ComposedExtendedModelResponse):
                    accumulated_commands.extend(inner_result.commands)
                    return inner_result.model_response
                if isinstance(inner_result, ExtendedModelResponse):
                    if inner_result.command is not None:
                        accumulated_commands.append(inner_result.command)
                    return inner_result.model_response
                return _normalize_to_model_response(inner_result)

            outer_result = await outer(request, inner_handle)
            return _to_composed_result(
                outer_result,
                extra_commands=accumulated_commands,
            )

        return composed

    composed_handler = composed_two(async_handlers[-2], async_handlers[-1])  # 列表最后一个和最后第二个进行链接
    for h in reversed(async_handlers[:-2]):
        composed_handler = composed_two(h, composed_handler)
    return composed_handler


def _get_model_call(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
):
    middleware_model_call = [
        m for m in middleware
        if m.__class__.wrap_model_call is not AgentMiddleware.wrap_model_call
           or m.__class__.awrap_model_call is not AgentMiddleware.awrap_model_call
    ]
    if middleware_model_call:
        sync_handlers = [
            m.wrap_model_call
            for m in middleware_model_call
        ]
        warp_model_call_handler = _chain_model_call(sync_handlers)

    return warp_model_call_handler


def _get_async_model_call(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
):
    middleware_async_model_call = [
        m for m in middleware
        if m.__class__.wrap_model_call is not AgentMiddleware.wrap_model_call
           or m.__class__.awrap_model_call is not AgentMiddleware.awrap_model_call
    ]
    if middleware_async_model_call:
        async_handlers = [
            m.awrap_model_call
            for m in middleware_async_model_call
        ]
        warp_model_call_handler = _chain_async_model_call(async_handlers)
    return warp_model_call_handler


def middleware_node(
        graph: StateGraph,
        merged_state_schema: type[NodeInputT],
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
) -> None:
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

        if (
                m.__class__.after_agent is not AgentMiddleware.after_agent
                or m.__class__.after_agent is not AgentMiddleware.after_agent
        ):
            sync_after_agent = (
                m.after_agent
                if m.__class__.after_agent is not AgentMiddleware.after_agent
                else None
            )
            async_after_agent = (
                m.aafter_agent
                if m.__class__.aafter_agent is not AgentMiddleware.aafter_agent
                else None
            )
            after_agent_node = RunnableCallable(sync_after_agent, async_after_agent)
            graph.add_node(
                f"{m.name}.after_agent",
                after_agent_node,
                input_schema=merged_state_schema
            )

        if (
                m.__class__.after_model is not AgentMiddleware.after_model
                or m.__class__.aafter_model is not AgentMiddleware.aafter_model
        ):
            sync_after_model = (
                m.after_model
                if m.__class__.after_model is not AgentMiddleware.after_model
                else None
            )
            async_after_model = (
                m.aafter_model
                if m.__class__.aafter_model is not AgentMiddleware.aafter_model
                else None
            )
            after_model_node = RunnableCallable(sync_after_model, async_after_model)
            graph.add_node(
                f"{m.name}.before_model",
                after_model_node,
                input_schema=merged_state_schema
            )


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


def _extract_metadata(field_type: type) -> list[Any]:
    """
    从字段中取出额外metadata数据
    :param field_type: schema的数值字段
    :return: 最终提取出的metadata列表
    """
    if get_origin(field_type) in {Required,NotRequired}:#如果field_type是Required[X]或NotRequired[X]
        inner_type=get_args(field_type)[0] #取出X
        if get_origin(inner_type) is Annotated:#如果X是Annotated[A,B,C]
            return list(get_args(inner_type)[1:])
    elif get_origin(field_type) is Annotated:#如果field_type是Annotated[A,B,C]
        return list(get_args(field_type)[1:])
    #以上形式都不是，说明field_type没有metadata数据，返回空列表
    #不写else,是因为get_origin(field_type)可能判为None，没有该分支判断
    return []


def __merged_schema(schemas: set[type], schema_name: str, omit_flag: str | None = None) -> type:
    all_annotations = {}
    for schema in schemas:
        hints = get_type_hints(schema, include_extras=True)  # 拿到 schema 里的字段定义（包括 Annotated 的 metadata）
        for field_name, field_type in hints.items():  # 遍历每一个字段，把合适的字段添加至all_annotations
            should_omit = False  # 默认设置不忽略
            if omit_flag:
                metadata = _extract_metadata(field_type)  # 提取metadata
                for meta in metadata:
                    if isinstance(meta, OmitFromSchema) or getattr(meta,omit_flag) is True:  # 判断是否是OmitFromSchema，是否匹配omit_flag
                        should_omit = True
                        break
            if not should_omit:
                all_annotations[field_name] = field_type
    return TypedDict(schema_name, all_annotations)


def _get_schema(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]]
):
    state_schemas: set[type] = {m.state_schema for m in middleware}
    merged_state_schema = __merged_schema(state_schemas,"StateSchema",None)  # 合并所有state_schema
    input_schema = __merged_schema(state_schemas,"InputSchema","input")  # 挑出输入
    output_schema = __merged_schema(state_schemas,"OutputSchema","output")  # 挑出输出

    return (state_schemas, merged_state_schema,
            input_schema, output_schema)


def _choose_tools_model_edge(
        tool_node,
        model_destinations,
        structured_output_tools,
        end_destination
):
    pass


def _choose_model_to_tools_edge(
        model_destinations,
        structured_output_tools,
        end_destination
):
    pass


def _add_middleware_edge(
        graph,
        name,
        default_destination,
        model_destination,
        end_destination,
        can_jump_to
):
    pass


def _get_can_jump_to(
        m1,
        param
):
    pass


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

    """wrap_model_call_handler"""
    wrap_model_call_handler = _get_model_call(middleware)

    """async_wrap_model_call_handler"""
    async_wrap_model_call_handler = _get_async_model_call(middleware)

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

    # TODO:实现model_node函数
    """添加model节点"""
    graph.add_node("model", RunnableCallable(model_node, amodel_node))

    """添加tools节点"""
    graph.add_node("tools", tool_node)

    """添加middleware节点"""
    middleware_node(graph, middleware)

    """构建从Start到entry_node的edge"""
    graph.add_edge(START, entry_node)

    """构建从tools到model的条件边"""
    # TODO:实现_choose_tools_model_edge函数
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

    """构建从loop_exit_node到出点的条件边"""
    # TODO:实现_choose_model_to_tools_edge函数
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
    # TODO:实现_add_middleware_edge函数
    # TODO:实现_get_can_jump_to函数
    for m1, m2 in itertools.pairwise(middleware_before_agent):  # 输入[A, B, C, D]，会输出(A, B), (B, C), (C, D)
        _add_middleware_edge(  # 两两连接中间件node
            graph,
            name=f"{m1.name}.before_agent",
            default_destination=f"{m2.name}.before_agent",
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_jump_to(m1, "before_agent"),
        )
    _add_middleware_edge(  # 将最后一个middleware node和loop_entry_node连接
        graph,
        name=f"{middleware_before_agent[-1].name}.before_agent",
        default_destination=loop_entry_node,
        model_destination=loop_entry_node,
        end_destination=exit_node,
        can_jump_to=_get_can_jump_to(middleware_before_agent[-1], "before_agent"),
    )

    """构建before_model middleware 边"""
    for m1, m2 in itertools.pairwise(middleware_before_model):
        _add_middleware_edge(
            graph,
            name=f"{m1.name}.before_model",
            default_destinantion=f"{m2.name}.before_model",
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_jump_to(m1, "before_model"),
        )
    _add_middleware_edge(
        graph,
        name=f"{middleware_before_model[-1].name}.before_model",
        default_destination="model",
        model_destination=loop_entry_node,
        end_destination=exit_node,
        can_jump_to=_get_can_jump_to(middleware_before_model[-1], "before_model"),
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
            can_jump_to=_get_can_jump_to(m1, "after_model"),
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
            can_jump_to=_get_can_jump_to(m1, "after_agent"),
        )
    _add_middleware_edge(
        graph,
        name=f"{middleware_after_agent[0].name}.after_agent",
        default_destiantion=END,
        model_destination=loop_entry_node,
        end_destination=exit_node,
        can_jump_to=_get_can_jump_to(middleware_after_agent[0], "after_agent"),
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
