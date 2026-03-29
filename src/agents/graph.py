import itertools
from dataclasses import field, dataclass
from typing import Sequence, Any, Callable, Awaitable, Generic, get_type_hints, Required, NotRequired, get_args, \
    Annotated

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
from mypyc.irbuild.util import TypedDict
from typing_extensions import get_origin
import logging

logging.basicConfig(level=logging.DEBUG)
logging.getLogger("langsmith").setLevel(logging.WARNING)
logger = logging.getLogger(__name__)


@dataclass  # 类似java的@data,自动创建__init__构造函数
class _ComposedExtendedModelResponse(Generic[ResponseT]):
    model_response: ModelResponse[ResponseT]
    commands: list[Command[Any]] = field(default_factory=list)  # field(default_factory)会在每次实例类时调用list函数创建list


def _get_binding_model(
        request: ModelRequest,
        tool_node: ToolNode,
) -> tuple[Runnable[Any, Any], ResponseFormat | None]:
    """获取绑定后的 model 和响应格式
    
    Args:
        request: 模型请求，包含 model、tools、response_format 等
        tool_node: 工具节点，包含可用的工具
    
    Returns:
        (bound_model, effective_response_format) 元组
        - bound_model: 绑定了 tools 的模型
        - effective_response_format: 实际使用的响应格式策略
    """
    # 从 tool_node 获取可用工具
    available_tools = list(tool_node.tools_by_name.values()) if tool_node else []

    # 获取请求中的 response_format
    response_format = request.response_format

    # 确定有效的 response_format（简化处理，直接使用请求的 format）
    effective_response_format: ResponseFormat | None = response_format

    # 根据 response_format 类型绑定模型
    if response_format is None:
        # 没有结构化输出，只绑定普通 tools
        if available_tools:
            bound_model = request.model.bind_tools(available_tools)
        else:
            bound_model = request.model
    else:
        # 有结构化输出需求，需要绑定 tools 和 response_format
        # ToolStrategy: 使用 tool calling 进行结构化输出
        # ProviderStrategy: 使用 provider 的原生结构化输出
        # AutoStrategy: 自动检测最佳策略
        bound_model = request.model.bind_tools(available_tools)

    return bound_model, effective_response_format


def _handle_model_output(
        output: AIMessage,
        effective_response_format: ResponseFormat | None
) -> dict[str, Any]:
    """处理模型输出，提取结构化响应
    
    Args:
        output: 模型输出的 AI 消息
        effective_response_format: 实际使用的响应格式策略
    
    Returns:
        包含 messages 和 structured_response 的字典
        - messages: 消息列表（至少包含 output）
        - structured_response: 结构化响应（如果有）
    
    简化处理逻辑：
    1. 如果是 ProviderStrategy → 尝试从 tool_calls 解析结构化响应
    2. 如果是 ToolStrategy → 尝试从匹配的 tool_call 解析结构化响应
    3. 其他情况 → 只返回 messages
    """
    from langchain_core.messages import ToolMessage
    from langchain.agents.structured_output import ProviderStrategy, ToolStrategy

    # 情况 1: ProviderStrategy - 使用 provider 原生结构化输出
    if isinstance(effective_response_format, ProviderStrategy):
        if output.tool_calls:
            # 有 tool calls，尝试解析结构化响应
            try:
                binding = ProviderStrategyBinding.from_schema_spec(
                    effective_response_format.schema_spec
                )
                # 从第一个 tool_call 解析
                # 简化处理：直接访问 args 属性
                first_tool_call = output.tool_calls[0]
                # 类型忽略：parse() 返回 dict，但这正是我们需要的结构化响应
                structured_response: Any = binding.parse(first_tool_call.get("args", {}))  # type: ignore[assignment]
                return {
                    "messages": [output],
                    "structured_response": structured_response
                }
            except Exception as exc:
                # 解析失败，抛出异常
                schema_name = getattr(
                    effective_response_format.schema_spec.schema,
                    "__name__",
                    "response_format"
                )
                raise ValueError(f"Failed to parse structured response for {schema_name}: {exc}") from exc
        # 没有 tool_calls，只返回 messages
        return {"messages": [output]}

    # 情况 2: ToolStrategy - 使用 tool calling 进行结构化输出
    if isinstance(effective_response_format, ToolStrategy) and output.tool_calls:
        # 查找匹配的结构化输出工具
        # 注意：这里简化处理，假设第一个 tool_call 就是我们要的
        first_tool_call = output.tool_calls[0]
        # 使用 .get() 方法避免类型错误
        tool_call_id = first_tool_call.get("id", "")
        tool_call_name = first_tool_call.get("name", "")
        tool_call_args: Any = first_tool_call.get("args", {})  # type: ignore[assignment]

        # 构建 ToolMessage 作为回应
        tool_message_content = (
                effective_response_format.tool_message_content
                or f"Returning structured response with args: {tool_call_args}"
        )

        return {
            "messages": [
                output,
                ToolMessage(
                    content=tool_message_content,
                    tool_call_id=tool_call_id,
                    name=tool_call_name,
                ),
            ],
            # 简化：直接返回 args 作为结构化响应
            "structured_response": tool_call_args
        }

    # 默认情况：没有结构化输出，只返回 messages
    return {"messages": [output]}


def _sync_execute_model(
        request: ModelRequest,
        tool_node: ToolNode,
) -> ModelResponse:
    model, effective_response = _get_binding_model(request, tool_node)  # 将外置配置绑定于model当中
    messages = request.messages
    if request.system_message:
        messages = [request.system_message, *messages]  # 整理 messages
    output = model.invoke(messages)
    handled_response = _handle_model_output(output, effective_response)  # 处理输出
    messages_list = handled_response["messages"]
    structured_response = handled_response.get("structured_response")

    return ModelResponse(
        result=messages_list,
        structured_response=structured_response
    )


async def _async_execute_model(
        request: ModelRequest,
        tool_node: ToolNode,
) -> ModelResponse:
    """异步执行模型调用并返回响应
    
    Args:
        request: 模型请求对象，包含 model、messages、response_format 等
    
    Returns:
        ModelResponse 对象，包含 messages 列表和可选的 structured_response
    
    简化处理逻辑：
    1. 调用 _get_binding_model 获取绑定后的模型和响应格式
    2. 整理 messages（如果有 system_message）
    3. 异步调用模型的 ainvoke 方法
    4. 使用 _handle_model_output 处理输出
    5. 构造并返回 ModelResponse
    """
    # 获取绑定后的模型和响应格式
    bound_model, effective_response = _get_binding_model(request, tool_node)

    # 准备 messages 列表
    messages = request.messages
    if request.system_message:
        # 如果有 system_message，放在消息列表最前面
        messages = [request.system_message, *messages]

    # 异步调用模型（非阻塞）
    output = await bound_model.ainvoke(messages)

    # 处理模型输出，提取结构化响应
    handled_response = _handle_model_output(output, effective_response)
    messages_list = handled_response["messages"]
    structured_response = handled_response.get("structured_response")

    # 构造 ModelResponse 返回
    return ModelResponse(
        result=messages_list,
        structured_response=structured_response
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
        system_messages:SystemMessage,
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
        system_messages:SystemMessage,
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

    # 获取异步 model_call 处理器
    async_handler = _get_async_model_call(middleware)

    if async_handler is None:  # 没有中间件处理器
        # 直接异步调用模型
        model_response = await _async_execute_model(request, tool_node)
        return _build_commands(model_response)

    # 有中间件处理器，通过它来调用
    result = await async_handler(request, lambda req: _async_execute_model(request, tool_node))
    return _build_commands(result.model_response, result.commands)


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
    all_annotations = {}
    for schema in schemas:
        hints = get_type_hints(schema, include_extras=True)  # 拿到 schema 里的字段定义（包括 Annotated 的 metadata）
        for field_name, field_type in hints.items():  # 遍历每一个字段，把合适的字段添加至all_annotations
            should_omit = False  # 默认设置不忽略
            if omit_flag:
                metadata = _extract_metadata(field_type)  # 提取metadata
                for meta in metadata:
                    if isinstance(meta, OmitFromSchema) or getattr(meta,
                                                                   omit_flag) is True:  # 判断是否是OmitFromSchema，是否匹配omit_flag
                        should_omit = True
                        break
            if not should_omit:
                all_annotations[field_name] = field_type
    return TypedDict(schema_name, all_annotations)


def _get_schema(
        middleware: Sequence[AgentMiddleware[StateT_co, ContextT]]
):
    from typing import List
    from langchain_core.messages import AnyMessage

    state_schemas: set[type] = {m.state_schema for m in middleware}

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
            "messages": List[AnyMessage]
        })
        return (state_schemas, StateSchema,
                InputSchema, OutputSchema)
    else:
        merged_state_schema = __merged_schema(state_schemas, "StateSchema", None)
        input_schema = __merged_schema(state_schemas, "InputSchema", "input")
        output_schema = __merged_schema(state_schemas, "OutputSchema", "output")

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
        # 这通常发生在：有工具调用但都已处理完毕，可能需要重试或继续
        return model_destinations

    return model_to_tools


def _get_can_jump_to(
        m1,
        param
) -> list[str] | None:
    """获取中间件节点可以跳转的目的地列表
    
    Args:
        m1: 中间件实例
        param: hook 类型 ('before_agent', 'before_model', 'after_model', 'after_agent')
    
    Returns:
        可跳转的目的地列表，如 ['model', 'end']，如果不能跳转则返回 None
    
    简化处理：
    - 检查中间件是否有 jump_to 属性
    - 如果有，返回对应的目的地列表
    - 否则返回 None，表示只能走默认路径
    """
    # 从中间件对象提取 jump_to 属性
    jump_to = getattr(m1, 'jump_to', None)

    if jump_to:
        # 如果有 jump_to，转换为列表
        if isinstance(jump_to, str):
            return [jump_to]
        elif isinstance(jump_to, list):
            return jump_to

    # 没有 jump_to，返回 None，表示不能跳转
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
    if can_jump_to is None or len(can_jump_to) == 0:
        # 情况 1：不能跳转，直接添加固定边
        graph.add_edge(name, default_destination)
    else:
        # 情况 2：可以跳转，添加条件边
        def jump_edge(state: dict[str, Any]) -> str:
            """根据 state 中的 jump_to 字段决定跳转到哪里"""
            # 从 state 中取出 jump_to 值
            jump_to_value = state.get("jump_to")

            # 简化处理：优先使用 jump_to 值
            if jump_to_value:
                # 如果 jump_to 是字符串，直接使用
                if isinstance(jump_to_value, str):
                    if jump_to_value == "model":
                        return model_destination
                    elif jump_to_value == "end":
                        return end_destination
                    elif jump_to_value == "tools":
                        return "tools"

            # 没有 jump_to 或无法识别，返回默认目的地
            return default_destination

        # 构建所有可能的目标节点列表
        destinations = [default_destination]

        # 根据 can_jump_to 添加额外的目标节点
        if "end" in can_jump_to and end_destination not in destinations:
            destinations.append(end_destination)
        if "model" in can_jump_to and model_destination not in destinations:
            destinations.append(model_destination)
        if "tools" in can_jump_to and "tools" not in destinations:
            destinations.append("tools")

        # 添加条件边
        graph.add_conditional_edges(
            name,
            RunnableCallable(jump_edge, trace=False),
            destinations
        )


def tool_node_wrapper(state: AgentState[Any], tool_node: ToolNode) -> dict:
    """ToolNode的包装器,用于添加日志"""
    logging.info("[TOOLS] >>> 进入tools节点")
    logging.debug(f"[TOOLS] 输入消息:{repr(state['messages'])}")
    logging.debug(f"[TOOLS] state完整信息:{repr(state)}")

    # 执行ToolNode
    result = tool_node.invoke(state)

    logging.info("[TOOLS] <<< 离开tools节点")
    logging.debug(f"[TOOLS] 输出消息:{repr(result.get('messages'))}")
    logging.debug(f"[TOOLS] 输出格式:{type(result)}")
    logging.debug(f"[TOOLS] 输出完整信息{repr(result)}")

    return result


def create_agent(
        model: str | BaseChatModel,
        tools: Sequence[BaseTool | Callable[..., Any] | dict[str, Any]]  = [],
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
    """系统提示词加载"""
    system_messages: SystemMessage | None = None
    if system_prompt :
        if isinstance(system_prompt,SystemMessage):
            system_messages=system_prompt
        else:
            system_messages=SystemMessage(content=system_prompt)
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
        return await amodel_node(
            model=model,
            tool_node=tool_node,
            system_messages=system_messages,
            middleware=middleware,
            initial_response_format=response_format,
            state=state,
            runtime=runtime
        )

    graph.add_node("model", RunnableCallable(model_node_wrapper, amodel_node_wrapper))

    """添加tools节点"""
    graph.add_node("tools", lambda state: tool_node_wrapper(state, tool_node))

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
            trace=False,
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

    """构建before_model middleware 边"""
    for m1, m2 in itertools.pairwise(middleware_before_model):
        _add_middleware_edge(
            graph,
            name=f"{m1.name}.before_model",
            default_destination=f"{m2.name}.before_model",
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_jump_to(m1, "before_model"),
        )
    if middleware_before_model:
        _add_middleware_edge(
            graph,
            name=f"{middleware_before_model[-1].name}.before_model",
            default_destination="model",
            model_destination=loop_entry_node,
            end_destination=exit_node,
            can_jump_to=_get_can_jump_to(middleware_before_model[-1], "before_model"),
        )

    """构建从 model 到 tools 的条件边"""
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

    config: RunnableConfig = {"recursion_limit": 10000}
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
