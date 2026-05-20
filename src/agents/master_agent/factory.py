import itertools
import asyncio
import logging
from dataclasses import field, dataclass
from typing import Sequence, Any, Callable, Awaitable, Generic, get_type_hints, Required, NotRequired, get_args, \
    Annotated

import langchain
from langchain.agents import AgentState
from langchain.agents.middleware import AgentMiddleware, ModelResponse, ExtendedModelResponse
from langchain.agents.middleware.types import StateT_co, ResponseT, ModelRequest, OmitFromSchema
from langchain.agents.structured_output import OutputToolBinding, ResponseFormat, ToolStrategy, ProviderStrategy, \
    AutoStrategy, ProviderStrategyBinding
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import ToolMessage, AIMessage, SystemMessage
from langchain_core.runnables import Runnable, RunnableConfig
from langchain_core.tools import BaseTool
from langgraph._internal._runnable import RunnableCallable  # type: ignore[import-not-top-level]
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
from typing import TypedDict
from typing_extensions import get_origin
import logging

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("langsmith").setLevel(logging.WARNING)
logging.getLogger("langchain").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@dataclass  # 类似java的@data,自动创建__init__构造函数
class _ComposedExtendedModelResponse(Generic[ResponseT]):
    model_response: ModelResponse[ResponseT]
    commands: list[Command[Any]] = field(default_factory=list)  # field(default_factory)会在每次实例类时调用list函数创建list


def _get_binding_model(
        request: ModelRequest,
        tool_node: ToolNode,
        structured_output_tools: dict[str, OutputToolBinding[Any]],
) -> tuple[Runnable[Any, Any], ResponseFormat | None]:
    """获取绑定后的 model 和响应格式

    Args:
        request: 模型请求，包含 model、tools、response_format 等
        tool_node: 工具节点，包含可用的工具
        structured_output_tools: 结构化输出工具字典

    Returns:
        (bound_model, effective_response_format) 元组
        - bound_model: 绑定了 tools 的模型
        - effective_response_format: 实际使用的响应格式策略
    """
    # 从 tool_node 获取可用工具
    available_tools = list(tool_node.tools_by_name.values()) if tool_node else []

    # 合并结构化输出工具
    final_tools = available_tools + [info.tool for info in structured_output_tools.values()]

    # 获取请求中的 response_format
    response_format = request.response_format
    effective_response_format: ResponseFormat | None = response_format

    # 根据 response_format 类型绑定模型
    if isinstance(response_format, ProviderStrategy):
        kwargs = response_format.to_model_kwargs()
        bound_model = request.model.bind_tools(final_tools, strict=True, **kwargs)
    elif isinstance(response_format, ToolStrategy):
        tool_choice = "any" if structured_output_tools else request.tool_choice
        bound_model = request.model.bind_tools(final_tools, tool_choice=tool_choice)
    else:
        if final_tools:
            bound_model = request.model.bind_tools(final_tools, tool_choice=request.tool_choice)
        else:
            bound_model = request.model

    return bound_model, effective_response_format


def _handle_model_output(
        output: AIMessage,
        effective_response_format: ResponseFormat | None,
        structured_output_tools: dict[str, OutputToolBinding[Any]]
) -> dict[str, Any]:
    """处理模型输出，提取结构化响应"""
    from langchain.agents.structured_output import ProviderStrategy, ToolStrategy

    # 情况 1: ProviderStrategy
    if isinstance(effective_response_format, ProviderStrategy):
        if not output.tool_calls:
            return {"messages": [output]}
        try:
            binding = ProviderStrategyBinding.from_schema_spec(effective_response_format.schema_spec)
            structured_response = binding.parse(output)
            return {"messages": [output], "structured_response": structured_response}
        except Exception as exc:
            schema_name = getattr(effective_response_format.schema_spec.schema, "__name__", "response_format")
            raise ValueError(f"Failed to parse structured response for {schema_name}: {exc}") from exc

    # 情况 2: ToolStrategy
    if isinstance(effective_response_format, ToolStrategy) and output.tool_calls:
        structured_tool_calls = [tc for tc in output.tool_calls if tc["name"] in structured_output_tools]
        if structured_tool_calls:
            tool_call = structured_tool_calls[0]
            try:
                binding = structured_output_tools[tool_call["name"]]
                structured_response = binding.parse(tool_call["args"])
                tool_message_content = effective_response_format.tool_message_content or f"Returning structured response: {structured_response}"
                return {
                    "messages": [
                        output,
                        ToolMessage(content=tool_message_content, tool_call_id=tool_call["id"], name=tool_call["name"]),
                    ],
                    "structured_response": structured_response,
                }
            except Exception as exc:
                error_msg = f"Error: {exc}\n Please fix your mistakes."
                return {
                    "messages": [
                        output,
                        ToolMessage(content=error_msg, tool_call_id=tool_call["id"], name=tool_call["name"]),
                    ],
                }

    return {"messages": [output]}


def _sync_execute_model(
        request: ModelRequest,
        tool_node: ToolNode,
        structured_output_tools: dict[str, OutputToolBinding[Any]],
) -> ModelResponse:
    model, effective_response = _get_binding_model(request, tool_node, structured_output_tools)
    messages = request.messages
    if request.system_message:
        messages = [request.system_message, *messages]
    output = model.invoke(messages)
    handled_response = _handle_model_output(output, effective_response, structured_output_tools)
    return ModelResponse(
        result=handled_response["messages"],
        structured_response=handled_response.get("structured_response")
    )


async def _async_execute_model(
        request: ModelRequest,
        tool_node: ToolNode,
        structured_output_tools: dict[str, OutputToolBinding[Any]],
) -> ModelResponse:
    """异步执行模型调用并返回响应"""
    bound_model, effective_response = _get_binding_model(request, tool_node, structured_output_tools)
    messages = request.messages
    if request.system_message:
        messages = [request.system_message, *messages]
    output = await bound_model.ainvoke(messages)
    logging.debug(f"[MODEL] output:{repr(output)}")
    handled_response = _handle_model_output(output, effective_response, structured_output_tools)
    return ModelResponse(
        result=handled_response["messages"],
        structured_response=handled_response.get("structured_response")
    )


def _build_commands(
        model_response: ModelResponse,
        middleware_commands: list[Command[Any]] | None = None
) -> list[Command[Any]]:
    """将模型响应转换为 Command 列表

    Args:
        model_response: 模型响应，包含 messages 和可选的 structured_response
        middleware_commands: 中间件积累的额外 commands（可选）

    Returns:
        Command 对象列表，第一个 Command 包含模型响应的状态更新

    简化处理逻辑：
    1. 从 model_response.result 提取 messages
    2. 如果有 structured_response，也加入状态
    3. 创建包含状态更新的 Command
    4. 追加中间件的 commands（如果有）
    """
    # 构建状态字典：包含 messages
    state: dict[str, Any] = {"messages": model_response.result}

    # 如果有结构化响应，也加入状态
    if model_response.structured_response is not None:
        state["structured_response"] = model_response.structured_response

    # 创建主 Command，包含状态更新
    commands: list[Command[Any]] = [Command(update=state)]

    # 追加中间件的 commands（如果有）
    if middleware_commands:
        commands.extend(middleware_commands)

    return commands


def model_node(
        model: str | BaseChatModel,
        tool_node: ToolNode,
        system_messages: SystemMessage,
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
        initial_response_format: ToolStrategy[Any] | ProviderStrategy[Any] | AutoStrategy[Any] | None,
        state: AgentState[Any],
        runtime: Runtime[ContextT],
) -> list[Command[Any]]:
    """定义 model_node"""
    logging.info("[MODEL NODE] >>> 进入 model 节点")

    #  验证 system_message
    if system_messages:
        logging.info(f"[MODEL NODE]  SystemMessage 已加载，长度:{len(system_messages.content)} 字符")
        logging.info(f"[MODEL NODE] SystemMessage 前 200 字符预览:\n{system_messages.content[:200]}...")
    else:
        logging.warning("[MODEL NODE]  SystemMessage 为空!")

    logging.debug(f"[MODEL NODE] 参数格式 model:{type(model)},tool_node {type(tool_node)},"
                  f"middleware:{type(middleware)},initial_response_format:{type(state)},"
                  f"state:{type(state)},runtime:{type(runtime)} ")
    logging.debug(f"[MODEL NODE] 输入消息数量:{len(state['messages'])}")
    logging.debug(f"[MODEL NODE] 输入消息格式:{repr(state['messages'])}")
    if state['messages']:
        last_msg = state['messages'][-1]
        logging.debug(f"[MODEL NODE] 最后一条消息类型：{type(last_msg).__name__}")
        logging.debug(f"[MODEL NODE] 最后一条消息内容：{str(last_msg.content)[:100]}")
        logging.debug(f"[MODEL NODE] 最后一条消息完整格式：{repr(last_msg)}")

    default_tools = []
    request = ModelRequest(  # 发送给LLM的标准数据包
        model=model,
        tools=default_tools,
        system_message=system_messages,
        response_format=initial_response_format,
        messages=state["messages"],
        tool_choice=None,
        state=state,
        runtime=runtime
    )

    # 在发送请求前，执行 before_model 中间件注入 state（同步版）
    for m in middleware:
        if m.__class__.before_model is not AgentMiddleware.before_model:
            try:
                injected = m.before_model(state, runtime, request)
                if injected is not None:
                    request = injected
            except Exception:
                pass  # 注入失败不影响主流程

    if _get_model_call(middleware) is None:  # 如果 model_call_handler 是 None
        model_response = _sync_execute_model(request, tool_node)  # 调用模型，执行操作，返回模型结果
        commands = _build_commands(model_response)

        logging.debug(f"[MODEL NODE] 模型响应消息数量:{len(model_response.result)}")
        logging.debug(f"[MODEL NODE] 模型响应消息格式:{repr(model_response)}")
        logging.debug(f"[MODEL NODE] 返回Commands完整格式:{repr(commands)}")
        logging.info(f"[MODEL NODE] <<< 离开model节点")

        return commands  # 把模型输出转换成 Agent 能执行的动作

    # 使用 lambda 包装，固定 middleware 和 tool_node 参数
    result = _get_model_call(middleware)(request, lambda req: _sync_execute_model(req, tool_node))
    return _build_commands(result.model_response, result.commands)  # 中间件组件可能有额外的 command


async def amodel_node(
        model: str | BaseChatModel,
        tool_node: ToolNode,
        system_messages: SystemMessage,
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
        initial_response_format: ToolStrategy[Any] | ProviderStrategy[Any] | AutoStrategy[Any] | None,
        state: AgentState[Any],
        runtime: Runtime[ContextT],
) -> list[Command[Any]]:
    """model_node 的异步函数

    Args:
        model: 模型实例或模型字符串
        middleware: 中间件列表
        initial_response_format: 初始响应格式策略
        state: agent 状态，包含 messages 等信息
        runtime: 运行时上下文

    Returns:
        Command 对象列表，包含状态更新和可选的结构化响应

    简化处理逻辑：
    1. 构建 ModelRequest 对象
    2. 检查是否有异步中间件处理器
    3. 如果没有 → 直接调用异步模型执行
    4. 如果有 → 通过中间件处理器调用
    5. 使用 _build_commands 转换为标准格式
    """

    default_tools = []
    request = ModelRequest(  # 发送给 LLM 的标准数据包
        model=model,
        tools=default_tools,
        system_message=system_messages,
        response_format=initial_response_format,
        messages=state["messages"],
        tool_choice=None,
        state=state,
        runtime=runtime
    )

    # 在发送请求前，执行 before_model 中间件注入 state
    for m in middleware:
        if m.__class__.abefore_model is not AgentMiddleware.abefore_model:
            try:
                injected = await m.abefore_model(state, runtime, request)
                if injected is not None:
                    request = injected
            except Exception:
                pass  # 注入失败不影响主流程

    # 获取异步 model_call 处理器
    async_handler = _get_async_model_call(middleware)

    if async_handler is None:  # 没有中间件处理器
        # 直接异步调用模型
        model_response = await _async_execute_model(request, tool_node, {})
        return _build_commands(model_response)

    # 有中间件处理器，通过它来调用
    result = await async_handler(request, lambda req: _async_execute_model(req, tool_node, {}))
    
    # 兼容处理：如果返回的是原生 ModelResponse，则没有 model_response 属性
    if hasattr(result, 'model_response'):
        return _build_commands(result.model_response, result.commands)
    else:
        # 原生 ModelResponse 或 AIMessage
        return _build_commands(result)


def _get_real_middleware_list(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
) -> (list, list, list, list):
    """hook函数列表"""
    # logging.info(f">>>>>>>>>>>>进入【_get_real_middleware_list】")
    # logging.debug(f"输入参数middleware:{repr(middleware)}")
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
    # logging.debug(f"输出结果before_agent:{repr(before_agent)}")
    # logging.debug(f"输出结果before_agent:{repr(before_model)}")
    # logging.debug(f"输出结果before_agent:{repr(after_model)}")
    # logging.debug(f"输出结果before_agent:{repr(after_agent)}")
    # logging.info(f"<<<<<<<<<<<<离开【_get_real_middleware_list】")


    return (before_agent, before_model,
            after_model, after_agent)


def _get_entry_node(
        before_agent: Sequence[AgentMiddleware[StateT_co, ContextT]],
        before_model: Sequence[AgentMiddleware[StateT_co, ContextT]],
) -> str:
    # logging.info(f">>>>>>>>>>>>进入【_get_entry_node】")
    # logging.debug(f"输入参数before_agent:{repr(before_agent)}")
    # logging.debug(f"输入参数before_agent:{repr(before_model)}")

    """entry_node节点判断"""
    if before_agent:
        entry_node = f"{before_agent[0].name}.before_agent"
    else:
        entry_node = "model"  # before_model 不再作为独立节点
    # logging.debug(f"输出结果before_agent:{repr(entry_node)}")
    # logging.info(f"<<<<<<<<<<<<离开【_get_entry_node】")
    return entry_node


def _get_loop_entry_node(
        before_model: Sequence[AgentMiddleware[StateT_co, ContextT]],
) -> str:
    """loop循环entry节点判断"""
    return "model"  # before_model 不再作为独立节点，直接在 model_node 内部执行


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
    # logging.info(f">>>>>>>>>>>>进入【_get_exit_node】")
    # logging.debug(f"输入参数after_agent:{repr(after_agent)}")
    if after_agent:
        exit_node = f"{after_agent[-1].name}.after_agent"
    else:
        exit_node = END
    # logging.debug(f"输出结果exit_node:{repr(exit_node)}")
    # logging.info(f"<<<<<<<<<<<<离开【_get_exit_node】")

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
    wrap_tool_call_wrapper = None  # 修复报错：局部变量 'wrap_tool_call_wrapper' 可能在赋值前引用
    if middleware:
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
    return None


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
        commands: list[Command[Any]] = list(extra_commands or [])
        
        # 1. 处理自定义的组合响应
        if isinstance(result, _ComposedExtendedModelResponse):
            commands.extend(result.commands)
            model_response = result.model_response
        # 2. 处理扩展响应
        elif isinstance(result, ExtendedModelResponse):
            model_response = result.model_response
            if result.command is not None:
                commands.append(result.command)
        # 3. 处理标准的 ModelResponse 或 AIMessage
        else:
            model_response = _normalize_to_model_response(result)
            
        return _ComposedExtendedModelResponse(model_response=model_response, commands=commands)

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

    if len(sync_handlers) == 0:
        return None
    if len(sync_handlers) == 1:
        return sync_handlers[0]

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

    if len(async_handlers) == 0:
        return None
    if len(async_handlers) == 1:
        return async_handlers[0]

    composed_handler = composed_two(async_handlers[-2], async_handlers[-1])  # 列表最后一个和最后第二个进行链接
    for h in reversed(async_handlers[:-2]):
        composed_handler = composed_two(h, composed_handler)
    return composed_handler


def _get_model_call(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]],
):
    warp_model_call_handler = None  # 修复报错:局部变量 'warp_model_call_handler' 可能在赋值前引用
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
    warp_model_call_handler = None  # 修复报错：局部变量 'warp_model_call_handler' 可能在赋值前引用
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
    # logging.info(f">>>>>>>>>>>>进入【middleware_node】")
    # logging.debug(f"输入参数 middleware:{repr(middleware)}")
    
    for m in middleware:
        # logging.debug(f"正在处理中间件: {m.name}")
        # before_agent
        if (
                m.__class__.before_agent is not AgentMiddleware.before_agent
                or m.__class__.abefore_agent is not AgentMiddleware.abefore_agent
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
            # logging.debug(f"-> 添加节点: {m.name}.before_agent")
            graph.add_node(
                f"{m.name}.before_agent",
                before_agent_node,
                input_schema=merged_state_schema
            )

        # before_model — 不在图中注册为独立节点，已在 amodel_node/model_node 内部执行
        # before_model 需要 (state, runtime, request) 三参数，独立节点只有 (state, runtime)
        # 因此改为在 model_node 内部直接调用 m.abefore_model(state, runtime, request)

        # after_agent
        if (
                m.__class__.after_agent is not AgentMiddleware.after_agent
                or m.__class__.aafter_agent is not AgentMiddleware.aafter_agent
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
            # logging.debug(f"-> 添加节点: {m.name}.after_agent")
            graph.add_node(
                f"{m.name}.after_agent",
                after_agent_node,
                input_schema=merged_state_schema
            )

        # after_model
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
            # logging.debug(f"-> 添加节点: {m.name}.after_model")
            graph.add_node(
                f"{m.name}.after_model",
                after_model_node,
                input_schema=merged_state_schema
            )
    
    # logging.info(f"<<<<<<<<<<<<离开【middleware_node】")


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
    # 处理 tools 为 None 的情况
    if tools is None:
        tools = []
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
    if get_origin(field_type) in {Required, NotRequired}:  # 如果field_type是Required[X]或NotRequired[X]
        inner_type = get_args(field_type)[0]  # 取出X
        if get_origin(inner_type) is Annotated:  # 如果X是Annotated[A,B,C]
            return list(get_args(inner_type)[1:])
    elif get_origin(field_type) is Annotated:  # 如果field_type是Annotated[A,B,C]
        return list(get_args(field_type)[1:])
    # 以上形式都不是，说明field_type没有metadata数据，返回空列表
    # 不写else,是因为get_origin(field_type)可能判为None，没有该分支判断
    return []


def __merged_schema(schemas: set[type], schema_name: str, omit_flag: str | None = None) -> type:
    # logging.info(f">>>>>>>>>>>>进入【__merged_schema】")
    # logging.debug(f"输入参数 schemas:{repr(schemas)}")
    # logging.debug(f"输入参数 schema_name:{schema_name}, omit_flag:{omit_flag}")
    
    from langchain.agents.middleware.types import OmitFromSchema
    
    all_annotations = {}
    for schema in schemas:
        hints = get_type_hints(schema, include_extras=True)
        for field_name, field_type in hints.items():
            should_omit = False
            if omit_flag:
                metadata = _extract_metadata(field_type)
                for meta in metadata:
                    # 1. 过滤 PrivateStateAttr (使用名称检查兼容不同版本)
                    if type(meta).__name__ == 'PrivateStateAttr':
                        should_omit = True
                        break
                    
                    # 2. 过滤 OmitFromSchema (安全获取属性)
                    if isinstance(meta, OmitFromSchema):
                        if getattr(meta, omit_flag, False):
                            should_omit = True
                            break
            if not should_omit:
                all_annotations[field_name] = field_type
                
    # logging.debug(f"合并结果 all_annotations:{all_annotations}")
    # logging.info(f"<<<<<<<<<<<<离开【__merged_schema】")
    return TypedDict(schema_name, all_annotations)


def _get_schema(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]]
):
    # logging.info(f">>>>>>>>>>>>进入【_get_schema】")
    # logging.debug(f"输入参数 middleware:{repr(middleware)}")
    import operator  # ← 新增导入
    from typing import List, Annotated  # ← 新增 Annotated
    from typing import List
    from langchain_core.messages import AnyMessage

    state_schemas: set[type] = {m.state_schema for m in middleware}
    # logging.debug(f"提取的中间件 schemas:{state_schemas}")

    # 如果没有中间件，使用默认的 messages schema
    if not state_schemas:
        # 创建默认的 input/output/state schema，都包含 messages 字段
        InputSchema = TypedDict("InputSchema", {
            "messages": List[AnyMessage]
        })
        OutputSchema = TypedDict("OutputSchema", {
            "messages": List[AnyMessage]
        })
        StateSchema = TypedDict("StateSchema", {
            # ↓ 修改这里：添加 operator.add 启用追加模式
            "messages": Annotated[List[AnyMessage], operator.add]  # 通过类型注解把 operator.add 函数注册为 messages 字段的合并策略
        })
        # logging.info(f"<<<<<<<<<<<<离开【_get_schema】（无中间件模式）")
        return (state_schemas, StateSchema,
                InputSchema, OutputSchema)
    else:
        merged_state_schema = __merged_schema(state_schemas, "StateSchema", None)
        input_schema = __merged_schema(state_schemas, "InputSchema", "input")
        output_schema = __merged_schema(state_schemas, "OutputSchema", "output")
        # logging.debug(f"生成 merged_state_schema:{merged_state_schema}")
        # logging.debug(f"生成 input_schema:{input_schema}")
        # logging.debug(f"生成 output_schema:{output_schema}")

    # logging.info(f"<<<<<<<<<<<<离开【_get_schema】")
    return (state_schemas, merged_state_schema,
            input_schema, output_schema)


def _choose_tools_model_edge(
        tool_node: ToolNode,
        model_destinations: str,
        structured_output_tools: dict[str, OutputToolBinding[Any]],
        end_destination: str
) -> Callable[[dict[str, Any]], str | None]:
    """创建从 tools 节点到 model 节点的路由函数

    Args:
        tool_node: 工具节点，用于检查工具是否已执行
        model_destinations: model 方向的目的地
        structured_output_tools: 结构化输出工具字典
        end_destination: 结束方向的目的地

    Returns:
        路由函数，根据工具执行情况决定下一个目的地

    简化处理逻辑：
    1. 检查是否有 jump_to → 有则跳转
    2. 检查所有执行的工具是否都有 return_direct=True → 是则结束
    3. 检查是否有结构化输出工具被执行 → 是则结束
    4. 默认 → 返回 model 继续循环
    """
    from langchain_core.messages import AIMessage, ToolMessage

    def tools_to_model(state: dict[str, Any]) -> str | None:
        """路由函数：根据工具执行情况决定下一步"""
        messages = state.get("messages", [])

        # 步骤 1: 获取最后一条 AI 消息和后续的 Tool 消息
        last_ai_message = None
        tool_messages = []

        # 从后往前找，找到最后一条 AIMessage
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], AIMessage):
                last_ai_message = messages[i]
                # 收集这条 AI 消息之后的所有 ToolMessage
                tool_messages = [
                    m for m in messages[i + 1:]
                    if isinstance(m, ToolMessage)
                ]
                break

        # 如果没有找到 AI 消息，直接去 model
        if last_ai_message is None:
            return model_destinations

        # 步骤 2: 检查是否有 jump_to 指令
        jump_to = state.get("jump_to")
        if jump_to:
            if jump_to == "end":
                return end_destination
            elif jump_to == "model":
                return model_destinations
            elif jump_to == "tools":
                return "tools"

        # 步骤 3: 检查所有 client-side 工具是否都有 return_direct=True
        client_side_tool_calls = [
            call for call in last_ai_message.tool_calls
            if call["name"] in tool_node.tools_by_name
        ]

        if client_side_tool_calls and all(
                tool_node.tools_by_name[call["name"]].return_direct
                for call in client_side_tool_calls
        ):
            # 所有工具都标记为 return_direct → 直接结束
            return end_destination

        # 步骤 4: 检查是否有结构化输出工具被执行
        if any(t.name in structured_output_tools for t in tool_messages):
            # 结构化输出工具已执行 → 结束
            return end_destination

        # 步骤 5: 默认情况 → 返回 model 继续处理
        return model_destinations

    return tools_to_model


def _choose_model_to_tools_edge(
        model_destinations: str,
        structured_output_tools: dict[str, OutputToolBinding[Any]],
        end_destination: str
) -> Callable[[dict[str, Any]], str | None]:
    """创建从 model 节点到 tools 节点的路由函数

    Args:
        model_destinations: model 方向的目的地（用于重试或继续循环）
        structured_output_tools: 结构化输出工具字典
        end_destination: 结束方向的目的地

    Returns:
        路由函数，根据模型输出决定下一个目的地

    简化处理逻辑：
    1. 检查是否有 jump_to → 有则跳转
    2. 检查是否有结构化响应 → 有则结束
    3. 检查模型是否调用了工具 → 没有则结束
    4. 检查是否有待处理的工具调用 → 有则去 tools
    5. 默认 → 返回 model 继续循环
    """
    from langchain_core.messages import AIMessage, ToolMessage

    def model_to_tools(state: dict[str, Any]) -> str | None:
        """路由函数：根据模型输出决定下一步"""
        messages = state.get("messages", [])

        # 步骤 1: 检查是否有 jump_to 指令
        jump_to = state.get("jump_to")
        if jump_to:
            if jump_to == "end":
                return end_destination
            elif jump_to == "model":
                return model_destinations
            elif jump_to == "tools":
                return "tools"

        # 步骤 2: 获取最后一条 AI 消息和后续的 Tool 消息
        last_ai_message = None
        tool_messages = []

        # 从后往前找，找到最后一条 AIMessage
        for i in range(len(messages) - 1, -1, -1):
            if isinstance(messages[i], AIMessage):
                last_ai_message = messages[i]
                # 收集这条 AI 消息之后的所有 ToolMessage
                tool_messages = [
                    m for m in messages[i + 1:]
                    if isinstance(m, ToolMessage)
                ]
                break

        # 如果没有找到 AI 消息，直接结束
        if last_ai_message is None:
            return end_destination

        # 步骤 3: 检查是否已经有结构化响应
        if "structured_response" in state:
            # 已有结构化响应 → 结束
            return end_destination

        # 步骤 4: 检查模型是否调用了工具
        if len(last_ai_message.tool_calls) == 0:
            # 没有工具调用 → 结束（经典的 agent 循环退出条件）
            return end_destination

        # 步骤 5: 找出待处理的工具调用
        # 已执行的工具调用会有对应的 ToolMessage，其 tool_call_id 与工具调用匹配
        tool_message_ids = [m.tool_call_id for m in tool_messages]

        pending_tool_calls = [
            call for call in last_ai_message.tool_calls
            if call["id"] not in tool_message_ids  # 尚未执行
               and call["name"] not in structured_output_tools  # 不是结构化输出工具
        ]

        # 如果有待处理的工具调用 → 去 tools 节点执行
        if pending_tool_calls:
            return "tools"

        # 步骤 6: 默认情况 → 返回 model 继续循环
        # 这通常发生在：有工具调用但都已处理完毕，需要 LLM 基于工具结果生成总结
        return model_destinations

    return model_to_tools


def _get_can_jump_to(
        m1,
        param
) -> list[str] | None:
    """获取中间件节点可以跳转的目的地列表"""
    # 获取中间件对应的方法
    method = getattr(m1.__class__, param, None)
    if not method:
        return None

    # 检查是否有 @hook_config 装饰器
    # LangGraph 的 hook_config 会将配置存储在方法的 __wrapped__ 或属性中
    # 简单做法：直接检查方法名是否在支持的跳转列表中
    # 对于 after_model，通常应该允许跳转到 end
    if param == "after_model":
        return ["end", "model", "tools"]  # after_model 中间件可以结束对话、跳回model或去tools执行
    elif param == "before_agent":
        return ["end"]  # before_agent只能选择继续或结束，不能跳回model
    elif param == "before_model":
        return ["model", "end"]

    return None


def _add_middleware_edge(
        graph,
        name: str,
        default_destination: str,
        model_destination: str,
        end_destination: str,
        can_jump_to: list[str] | None,
) -> None:
    """为中间件节点添加边到 graph

    Args:
        graph: StateGraph 对象
        name: 中间件节点的名称
        default_destination: 默认目的地
        model_destination: model 方向的目的地
        end_destination: 结束方向的目的地
        can_jump_to: 允许跳转的目的地列表，如 ['model', 'end']

    简化处理逻辑：
    1. 如果 can_jump_to 为 None → 添加普通边（固定路径）
    2. 如果 can_jump_to 不为 None → 添加条件边（根据 jump_to 字段动态决定路径）
    """
    # print(f"[DEBUG _add_middleware_edge] name={name}, default={default_destination}, model_dest={model_destination}, end_dest={end_destination}, can_jump={can_jump_to}")
    if can_jump_to is None or len(can_jump_to) == 0:
        # 情况 1：不能跳转，直接添加固定边
        graph.add_edge(name, default_destination)
    else:
        # 情况 2：可以跳转，添加条件边
        def jump_edge(state: dict[str, Any]) -> str:
            """根据 state 中的 jump_to 字段决定跳转到哪里"""
            jump_to_value = state.get("jump_to")

            if isinstance(jump_to_value, str):
                # 必须将 "end"/"model" 解析为实际节点名，
                # 否则 LangGraph 的 Branch._finish 会 KeyError
                if jump_to_value == "end":
                    return end_destination
                elif jump_to_value == "model":
                    return model_destination
                elif jump_to_value == "tools":
                    return "tools"
                return jump_to_value  # 未知值回退（落入 destinations 列表）

            # 没有 jump_to, 返回默认目的地
            return default_destination

        # 构建所有可能的目标节点列表
        destinations = [default_destination]

        # 根据 can_jump_to 添加额外的目标节点
        if "end" in can_jump_to and end_destination not in destinations:
            destinations.append(end_destination)
        if "model" in can_jump_to:
            # model_destination可能是变量（如"gap_detector.before_model"）或字符串"model"
            if model_destination not in destinations:
                destinations.append(model_destination)
            # 同时添加字符串"model"以兼容直接跳转
            if "model" not in destinations:
                destinations.append("model")
        if "tools" in can_jump_to and "tools" not in destinations:
            destinations.append("tools")
        
        # print(f"[DEBUG destinations] name={name}, destinations={destinations}")

        # 添加条件边
        graph.add_conditional_edges(
            name,
            RunnableCallable(jump_edge, trace=False),
            destinations
        )


async def tool_node_wrapper(state: AgentState[Any], tool_node: ToolNode) -> dict:
    """ToolNode的异步包装器,用于添加日志和增强并行稳定性

    重要：DeepSeek 要求每个 ToolMessage 的 tool_call_id 必须匹配前一条 AIMessage 中的
    tool_calls。因此当 ToolMessage 缺少 tool_call_id 时，不能随机生成 UUID，而应从
    前一条 AIMessage 的 tool_calls 中按位置匹配。
    """
    from langchain_core.messages import BaseMessage, AIMessage, ToolMessage
    from langgraph.types import Command

    result = await tool_node.ainvoke(state)

    # 从前一条 AIMessage 提取 tool_call_ids，用于回填空的 tool_call_id
    _fallback_ids = []
    for msg in reversed(state.get("messages", [])):
        if isinstance(msg, AIMessage) and msg.tool_calls:
            _fallback_ids = [tc["id"] for tc in msg.tool_calls if tc.get("id")]
            break

    # 兼容处理：tool_node.ainvoke 可能返回 list 或 dict
    if isinstance(result, list):
        all_updates = {}
        valid_messages = []
        _fallback_idx = 0

        for item in result:
            if isinstance(item, BaseMessage):
                if isinstance(item, ToolMessage) and not item.tool_call_id:
                    if _fallback_idx < len(_fallback_ids):
                        item.tool_call_id = _fallback_ids[_fallback_idx]
                        logging.info(f"[TOOLS] 从 AIMessage 回填 tool_call_id: {item.tool_call_id}")
                    else:
                        logging.warning(
                            f"[TOOLS] ToolMessage 缺少 tool_call_id 且无法匹配，"
                            f"工具名={item.name}，跳过该消息以避免 DeepSeek 400 错误"
                        )
                        _fallback_idx += 1
                        continue  # 跳过无法匹配的 ToolMessage
                    _fallback_idx += 1
                valid_messages.append(item)
            elif isinstance(item, Command):
                if item.update:
                    if 'messages' in item.update:
                        fixed_messages = []
                        for msg in item.update['messages']:
                            if isinstance(msg, ToolMessage) and not msg.tool_call_id:
                                if _fallback_idx < len(_fallback_ids):
                                    msg.tool_call_id = _fallback_ids[_fallback_idx]
                                    logging.info(f"[TOOLS] 从 AIMessage 回填 Command 中的 tool_call_id: {msg.tool_call_id}")
                                else:
                                    logging.warning(
                                        f"[TOOLS] Command 中的 ToolMessage 缺少 tool_call_id 且无法匹配，"
                                        f"工具名={msg.name}，跳过该消息"
                                    )
                                    _fallback_idx += 1
                                    continue
                                _fallback_idx += 1
                            fixed_messages.append(msg)
                        item.update['messages'] = fixed_messages
                        valid_messages.extend(fixed_messages)

                    for key, value in item.update.items():
                        if key != 'messages':
                            all_updates[key] = value
            else:
                pass

        final_result = {"messages": valid_messages}
        final_result.update(all_updates)

        logging.debug(f"[TOOLS] 输出有效消息列表长度: {len(valid_messages)}")
        logging.debug(f"[TOOLS] 输出完整信息: {repr(final_result)}")
        return final_result
    elif isinstance(result, dict):
        logging.debug(f"[TOOLS] 输出消息:{repr(result.get('messages'))}")
        logging.debug(f"[TOOLS] 输出格式:{type(result)}")
        logging.debug(f"[TOOLS] 输出完整信息{repr(result)}")
        return result
    else:
        logging.error(f"[TOOLS] 未知返回类型: {type(result)}, 内容: {result}")
        return {}




def create_agent(
        model: str | BaseChatModel,
        tools: Sequence[BaseTool | Callable[..., Any] | dict[str, Any]] = [],
        *,
        system_prompt: str | SystemMessage | None = None,
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
    # logging.info(f">>>>>>>>>>>>进入[factory]")

    """系统提示词加载"""
    system_messages: SystemMessage | None = None
    if system_prompt:
        if isinstance(system_prompt, SystemMessage):
            system_messages = system_prompt
        else:
            system_messages = SystemMessage(content=system_prompt)
    # logging.info(f"[system_messages]:{system_messages}")
    # logging.debug(f"[system_messages]:{repr(system_messages)}")

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

    """tool 节点之后的节点方向"""
    # exit_node 必须始终包含在 destinations 中，因为 jump_to 可能指向它
    tools_to_model_destinations = [loop_entry_node, exit_node]
    if (
            any(tool.return_direct for tool in tool_node.tools_by_name.values())
            or structured_output_tools
    ):
        # 已经有 exit_node 了，不需要重复添加
        pass

    """model节点之后的节点方向"""
    model_to_tools_destinations = ["tools", exit_node]
    if response_format or loop_exit_node != "model":
        model_to_tools_destinations.append(loop_entry_node)

    """四大 schema"""
    (state_schemas, merged_state_schema,
     input_schema, output_schema) = _get_schema(middleware)

    """建 graph"""
    graph: StateGraph = StateGraph(
        state_schema=merged_state_schema,  # type: ignore[arg-type]
        input_schema=input_schema,  # type: ignore[arg-type]
        output_schema=output_schema,  # type: ignore[arg-type]
        context_schema=context_schema,
    )

    """添加 model 节点"""

    def model_node_wrapper(state: AgentState[Any], runtime: Runtime[ContextT]) -> list[Command[Any]]:
        logging.info("[MODEL] >>> 进入model节点")

        return model_node(
            model=model,
            tool_node=tool_node,
            system_messages=system_messages,
            middleware=middleware,
            initial_response_format=response_format,
            state=state,
            runtime=runtime
        )

    async def amodel_node_wrapper(state: AgentState[Any], runtime: Runtime[ContextT]) -> list[Command[Any]]:
        import logging
        logging.info("[MODEL] >>> 进入model节点")
        try:
            result = await amodel_node(
                model=model,
                tool_node=tool_node,
                system_messages=system_messages,
                middleware=middleware,
                initial_response_format=response_format,
                state=state,
                runtime=runtime
            )
            logging.info(f"[MODEL] <<< 离开model节点, 返回类型: {type(result)}, 长度: {len(result) if isinstance(result, (list, dict)) else 'N/A'}")
            return result
        except Exception as e:
            logging.error(f"[MODEL] 节点异常: {type(e).__name__}: {e}", exc_info=True)
            raise

    graph.add_node("model", RunnableCallable(model_node_wrapper, amodel_node_wrapper))

    """添加tools节点"""
    async def atool_node_wrapper(state):
        return await tool_node_wrapper(state, tool_node)

    graph.add_node("tools", RunnableCallable(None, afunc=atool_node_wrapper))

    """添加 middleware 节点"""
    middleware_node(graph, merged_state_schema, middleware)  # type: ignore[arg-type]

    """构建从Start到entry_node的edge"""
    graph.add_edge(START, entry_node)

    """构建从 tools 到 model 的条件边"""
    graph.add_conditional_edges(
        "tools",
        RunnableCallable(  # type: ignore[arg-type]
            _choose_tools_model_edge(
                tool_node=tool_node,
                model_destinations=loop_entry_node,
                structured_output_tools=structured_output_tools,
                end_destination=exit_node,
            ),
            trace=True,
        ),
        tools_to_model_destinations,  # 目标节点列表
    )

    """构建 before_agent middleware 边"""
    for m1, m2 in itertools.pairwise(middleware_before_agent):  # 输入[A, B, C, D]，会输出(A, B), (B, C), (C, D)
        _add_middleware_edge(  # 两两连接中间件node
            graph,
            name=f"{m1.name}.before_agent",
            default_destination=f"{m2.name}.before_agent",
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_jump_to(m1, "before_agent"),
        )
    if middleware_before_agent:
        _add_middleware_edge(  # 将最后一个middleware node和loop_entry_node连接
            graph,
            name=f"{middleware_before_agent[-1].name}.before_agent",
            default_destination=loop_entry_node,
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_jump_to(middleware_before_agent[-1], "before_agent"),
        )

    # before_model 不再注册为独立节点，已在 model_node 内部直接调用
    # 无需构建 before_model 边

    """构建从 model 到 tools 的条件边"""
    if not middleware_after_model:
        graph.add_conditional_edges(
            "model",
            RunnableCallable(  # type: ignore[arg-type]
                _choose_model_to_tools_edge(
                    model_destinations=loop_entry_node,
                    structured_output_tools=structured_output_tools,
                    end_destination=exit_node
                ),
                trace=False,
            ),
            model_to_tools_destinations,  # 使用正确的目标列表
        )



    """构建 after_model middleware 边"""
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
    
    # 处理第一个中间件（链条出口，即最后注册的中间件）
    if middleware_after_model:
        _add_middleware_edge(
            graph,
            name=f"{middleware_after_model[0].name}.after_model",
            default_destination=exit_node,
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_jump_to(middleware_after_model[0], "after_model"),
        )
    # Model 节点不具备重新回到 model 节点和直接退出的功能，否则过于冗余
    if middleware_after_model:
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
    if middleware_after_agent:
        _add_middleware_edge(
            graph,
            name=f"{middleware_after_agent[0].name}.after_agent",
            default_destination=END,
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_jump_to(middleware_after_agent[0], "after_agent"),
        )

    config: RunnableConfig = {"recursion_limit": 25}
    if name:
        config["metadata"] = {"agent_name": name}

    # 添加 LangSmith tracer（如果启用了 tracing）
    import os
    if os.getenv("LANGSMITH_TRACING") == "true":
        try:
            from langchain_core.tracers import LangChainTracer
            config["callbacks"] = [LangChainTracer()]
        except:
            pass

    return graph.compile(  # type: ignore[return-value]
        checkpointer=checkpointer,
        store=store,
        interrupt_before=interrupt_before,
        interrupt_after=interrupt_after,
        debug=debug,
        name=name,
        cache=cache,
    ).with_config(config)
