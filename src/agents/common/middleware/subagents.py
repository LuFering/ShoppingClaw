"""Middleware for providing subagents to an agent via a `task` tool."""

import json
import logging
import re
import warnings
from collections.abc import Awaitable, Callable, Sequence
from typing import Annotated, Any, NotRequired, TypedDict, Unpack, cast
from langchain_core.messages import AIMessage
from langchain.agents import create_agent
from langchain.agents.middleware import HumanInTheLoopMiddleware, InterruptOnConfig
from langchain.agents.middleware.types import AgentMiddleware, ContextT, ModelRequest, ModelResponse, ResponseT
from langchain.chat_models import init_chat_model
from langchain.tools import BaseTool, ToolRuntime
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import StructuredTool
from langgraph.config import get_stream_writer
from langgraph.types import Command

from src.agents.common.backends import BackendProtocol
from src.agents.common.backends.protocol import BackendFactory
from src.agents.common.middleware._utils import append_to_system_message

"""未编译形态的subagent"""
class SubAgent(TypedDict):
    """Specification for an agent.

    When using `create_deep_agent`, subagents automatically receive a default middleware
    stack (TodoListMiddleware, FilesystemMiddleware, SummarizationMiddleware, etc.) before
    any custom `middleware` specified in this spec.

    Required fields:
        name: Unique identifier for the subagent.

            The main agent uses this name when calling the `task()` tool.
        description: What this subagent does.

            Be specific and action-oriented. The main agent uses this to decide when to delegate.
        system_prompt: Instructions for the subagent.

            Include tool usage guidance and output format requirements.

    Optional fields:
        tools: Tools the subagent can use.

            If not specified, inherits tools from the main agent via `default_tools`.
        model: Override the main agent's model.

            Use the format `'provider:model-name'` (e.g., `'openai:gpt-4o'`).
        middleware: Additional middleware for custom behavior, logging, or rate limiting.
        interrupt_on: Configure human-in-the-loop for specific tools.

            Requires a checkpointer.
        skills: Skill source paths for SkillsMiddleware.

            List of paths to skill directories (e.g., `["/skills/user/", "/skills/project/"]`).
    """

    name: str
    """Unique identifier for the subagent."""

    description: str
    """What this subagent does. The main agent uses this to decide when to delegate."""

    system_prompt: str
    """Instructions for the subagent."""

    tools: NotRequired[Sequence[BaseTool | Callable | dict[str, Any]]]
    """Tools the subagent can use. If not specified, inherits from main agent."""

    model: NotRequired[str | BaseChatModel]
    """Override the main agent's model. Use `'provider:model-name'` format."""

    middleware: NotRequired[list[AgentMiddleware]]
    """Additional middleware for custom behavior."""

    interrupt_on: NotRequired[dict[str, bool | InterruptOnConfig]]
    """Configure human-in-the-loop for specific tools."""

    skills: NotRequired[list[str]]
    """Skill source paths for SkillsMiddleware."""

"""已编译形态的subagent"""
class CompiledSubAgent(TypedDict):
    """A pre-compiled agent spec.

    !!! note

        The runnable's state schema must include a 'messages' key.

        This is required for the subagent to communicate results back to the main agent.

    When the subagent completes, the final message in the 'messages' list will be
    extracted and returned as a `ToolMessage` to the parent agent.
    """

    name: str
    """Unique identifier for the subagent."""

    description: str
    """What this subagent does."""

    runnable: Runnable
    """A custom agent implementation.

    Create a custom agent using either:

    1. LangChain's [`create_agent()`](https://docs.langchain.com/oss/python/langchain/quickstart)
    2. A custom graph using [`langgraph`](https://docs.langchain.com/oss/python/langgraph/quickstart)

    If you're creating a custom graph, make sure the state schema includes a 'messages' key.
    This is required for the subagent to communicate results back to the main agent.
    """


DEFAULT_SUBAGENT_PROMPT = "In order to complete the objective that the user asks of you, you have access to a number of standard tools."

# State keys that are excluded when passing state to subagents and when returning
# updates from subagents.
#
# When returning updates:
# 1. The messages key is handled explicitly to ensure only the final message is included
# 2. The todos and structured_response keys are excluded as they do not have a defined reducer
#    and no clear meaning for returning them from a subagent to the main agent.
# 3. The skills_metadata and memory_contents keys are automatically excluded from subagent output
#    via PrivateStateAttr annotations on their respective state schemas. However, they must ALSO
#    be explicitly filtered from runtime.state when invoking a subagent to prevent parent state
#    from leaking to child agents (e.g., the general-purpose subagent loads its own skills via
#    SkillsMiddleware).
_EXCLUDED_STATE_KEYS = {"messages", "todos", "structured_response", "skills_metadata", "memory_contents"}


# ---------------------------------------------------------------------------
# SubAgent 输出协议校验 + 证据注入
# ---------------------------------------------------------------------------

def _get_output_schema(subagent_type: str):
    """按 Agent 类型获取对应的 Pydantic 输出协议（懒加载，避免循环依赖）。"""
    try:
        from agents.common.model import (
            ResearcherOutput,
            AnalystOutput,
            CriticOutput,
            MemoryOutput,
        )
        _SCHEMA_MAP = {
            "researcher": ResearcherOutput,
            "analyst": AnalystOutput,
            "critic": CriticOutput,
            "memory_manager": MemoryOutput,
        }
        return _SCHEMA_MAP.get(subagent_type)
    except ImportError:
        return None


def _enrich_task_description(subagent_type: str, description: str, state: dict) -> str:
    """将 MasterAgent state 中的前置证据注入到 SubAgent 的任务描述中。

    确保下游 Agent（analyst／critic）能接收到上游 Agent 已产出的数据，
    无需 MasterAgent 在 prompt 中手动传递。
    """
    evidence = state.get("evidence", {})

    if subagent_type == "analyst":
        research_data = evidence.get("research_data")
        if research_data and research_data.get("products"):
            products_str = json.dumps(
                research_data["products"], ensure_ascii=False, indent=2
            )
            description = (
                f"{description}\n\n"
                f"【系统注入】以下为 Researcher 已采集的商品数据，请基于此进行分析：\n{products_str}"
            )

    elif subagent_type == "critic":
        analysis_report = evidence.get("analysis_report")
        if analysis_report:
            report_str = json.dumps(analysis_report, ensure_ascii=False, indent=2)
            description = (
                f"{description}\n\n"
                f"【系统注入】以下为 Analyst 的分析报告，请据此进行风险评估：\n{report_str}"
            )

    return description


def _extract_json(text: str) -> dict | None:
    """从可能包含 Markdown 或前言的文本中提取 JSON 对象。"""
    # 检测并警告 ```json 不合规输出
    if '```' in text:
        logging.warning(
            f"[SubAgent] 输出包含 ```json 标记（违反 prompt 约束），"
            f"_extract_json 已兼容提取，但应约束 LLM 遵守纯 JSON 协议"
        )

    # 1. 直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 2. ```json ... ``` 块
    match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # 3. 第一个 { ... } 块
    match = re.search(r'\{[\s\S]*\}', text)
    if match:
        try:
            return json.loads(match.group(0))
        except json.JSONDecodeError:
            pass

    return None


def _validate_output(subagent_type: str, text: str) -> tuple[bool, str | None]:
    """校验 SubAgent 输出是否符合约定的 Pydantic Schema，并返回含默认值的完整 JSON。

    Returns:
        (is_valid, result_or_error)
        - is_valid=True 时 result_or_error 为经过 Pydantic 填充默认值后的完整 JSON 字符串
        - is_valid=False 时 result_or_error 为错误提示
    """
    schema = _get_output_schema(subagent_type)
    if schema is None:
        return True, text  # 没有定义 Schema 的 Agent 类型，原样返回

    parsed = _extract_json(text)
    if parsed is None:
        return False, (
            f"输出格式错误：未检测到有效的 JSON 对象。请只输出一个符合 "
            f"{schema.__name__} 格式的纯 JSON 对象，不要包含任何 Markdown "
            f"标记（```json）、开场白或结束语。"
        )

    try:
        validated = schema.model_validate(parsed)
        return True, validated.model_dump_json(ensure_ascii=False)
    except Exception as e:
        # 宽松校验降级：model_validate 可能因工具返回数据不完整（缺 price/state/url 等）
        # 而失败。使用 model_construct 跳过验证，让数据流继续
        try:
            validated = schema.model_construct(**parsed)
            logging.warning(
                f"[SubAgent] {subagent_type} 宽松验证通过（model_construct），"
                f"跳过严格校验。原始错误: {e}"
            )
            return True, validated.model_dump_json(ensure_ascii=False)
        except Exception:
            return False, (
                f"输出验证失败：{e}\n"
                f"请根据以上错误修正输出，只返回符合 {schema.__name__} 格式的纯 JSON 对象。"
            )


# ---------------------------------------------------------------------------
# 下面为 Task Tool 构建逻辑
# ---------------------------------------------------------------------------

TASK_TOOL_DESCRIPTION = """Launch an ephemeral subagent to handle complex, multi-step independent tasks with isolated context windows.

Available agent types and the tools they have access to:
{available_agents}

When using the Task tool, you must specify a subagent_type parameter to select which agent type to use.

## Usage notes:
1. Launch multiple agents concurrently whenever possible, to maximize performance; to do that, use a single message with multiple tool uses
2. When the agent is done, it will return a single message back to you. The result returned by the agent is not visible to the user. To show the user the result, you should send a text message back to the user with a concise summary of the result.
3. Each agent invocation is stateless. You will not be able to send additional messages to the agent, nor will the agent be able to communicate with you outside of its final report. Therefore, your prompt should contain a highly detailed task description for the agent to perform autonomously and you should specify exactly what information the agent should return back to you in its final and only message to you.
4. The agent's outputs should generally be trusted
5. Clearly tell the agent whether you expect it to create content, perform analysis, or just do research (search, file reads, web fetches, etc.), since it is not aware of the user's intent
6. If the agent description mentions that it should be used proactively, then you should try your best to use it without the user having to ask for it first. Use your judgement.
7. When only the general-purpose agent is provided, you should use it for all tasks. It is great for isolating context and token usage, and completing specific, complex tasks, as it has all the same capabilities as the main agent.

### Example usage of the general-purpose agent:

<example_agent_descriptions>
"general-purpose": use this agent for general purpose tasks, it has access to all tools as the main agent.
</example_agent_descriptions>

<example>
User: "I want to conduct research on the accomplishments of Lebron James, Michael Jordan, and Kobe Bryant, and then compare them."
Assistant: *Uses the task tool in parallel to conduct isolated research on each of the three players*
Assistant: *Synthesizes the results of the three isolated research tasks and responds to the User*
<commentary>
Research is a complex, multi-step task in it of itself.
The research of each individual player is not dependent on the research of the other players.
The assistant uses the task tool to break down the complex objective into three isolated tasks.
Each research task only needs to worry about context and tokens about one player, then returns synthesized information about each player as the Tool Result.
This means each research task can dive deep and spend tokens and context deeply researching each player, but the final result is synthesized information, and saves us tokens in the long run when comparing the players to each other.
</commentary>
</example>

<example>
User: "Analyze a single large code repository for security vulnerabilities and generate a report."
Assistant: *Launches a single `task` subagent for the repository analysis*
Assistant: *Receives report and integrates results into final summary*
<commentary>
Subagent is used to isolate a large, context-heavy task, even though there is only one. This prevents the main thread from being overloaded with details.
If the user then asks followup questions, we have a concise report to reference instead of the entire history of analysis and tool calls, which is good and saves us time and money.
</commentary>
</example>

<example>
User: "Schedule two meetings for me and prepare agendas for each."
Assistant: *Calls the task tool in parallel to launch two `task` subagents (one per meeting) to prepare agendas*
Assistant: *Returns final schedules and agendas*
<commentary>
Tasks are simple individually, but subagents help silo agenda preparation.
Each subagent only needs to worry about the agenda for one meeting.
</commentary>
</example>

<example>
User: "I want to order a pizza from Dominos, order a burger from McDonald's, and order a salad from Subway."
Assistant: *Calls tools directly in parallel to order a pizza from Dominos, a burger from McDonald's, and a salad from Subway*
<commentary>
The assistant did not use the task tool because the objective is super simple and clear and only requires a few trivial tool calls.
It is better to just complete the task directly and NOT use the `task`tool.
</commentary>
</example>

### Example usage with custom agents:

<example_agent_descriptions>
"content-reviewer": use this agent after you are done creating significant content or documents
"greeting-responder": use this agent when to respond to user greetings with a friendly joke
"research-analyst": use this agent to conduct thorough research on complex topics
</example_agent_description>

<example>
user: "Please write a function that checks if a number is prime"
assistant: Sure let me write a function that checks if a number is prime
assistant: First let me use the Write tool to write a function that checks if a number is prime
assistant: I'm going to use the Write tool to write the following code:
<code>
function isPrime(n) {{
  if (n <= 1) return false
  for (let i = 2; i * i <= n; i++) {{
    if (n % i === 0) return false
  }}
  return true
}}
</code>
<commentary>
Since significant content was created and the task was completed, now use the content-reviewer agent to review the work
</commentary>
assistant: Now let me use the content-reviewer agent to review the code
assistant: Uses the Task tool to launch with the content-reviewer agent
</example>

<example>
user: "Can you help me research the environmental impact of different renewable energy sources and create a comprehensive report?"
<commentary>
This is a complex research task that would benefit from using the research-analyst agent to conduct thorough analysis
</commentary>
assistant: I'll help you research the environmental impact of renewable energy sources. Let me use the research-analyst agent to conduct comprehensive research on this topic.
assistant: Uses the Task tool to launch with the research-analyst agent, providing detailed instructions about what research to conduct and what format the report should take
</example>

<example>
user: "Hello"
<commentary>
Since the user is greeting, use the greeting-responder agent to respond with a friendly joke
</commentary>
assistant: "I'm going to use the Task tool to launch with the greeting-responder agent"
</example>"""  # noqa: E501

TASK_SYSTEM_PROMPT = """## `task` (subagent spawner)

You have access to a `task` tool to launch short-lived subagents that handle isolated tasks. These agents are ephemeral — they live only for the duration of the task and return a single result.

When to use the task tool:
- When a task is complex and multi-step, and can be fully delegated in isolation
- When a task is independent of other tasks and can run in parallel
- When a task requires focused reasoning or heavy token/context usage that would bloat the orchestrator thread
- When sandboxing improves reliability (e.g. code execution, structured searches, data formatting)
- When you only care about the output of the subagent, and not the intermediate steps (ex. performing a lot of research and then returned a synthesized report, performing a series of computations or lookups to achieve a concise, relevant answer.)

Subagent lifecycle:
1. **Spawn** → Provide clear role, instructions, and expected output
2. **Run** → The subagent completes the task autonomously
3. **Return** → The subagent provides a single structured result
4. **Reconcile** → Incorporate or synthesize the result into the main thread

When NOT to use the task tool:
- If you need to see the intermediate reasoning or steps after the subagent has completed (the task tool hides them)
- If the task is trivial (a few tool calls or simple lookup)
- If delegating does not reduce token usage, complexity, or context switching
- If splitting would add latency without benefit

## Important Task Tool Usage Notes to Remember
- Whenever possible, parallelize the work that you do. This is true for both tool_calls, and for tasks. Whenever you have independent steps to complete - make tool_calls, or kick off tasks (subagents) in parallel to accomplish them faster. This saves time for the user, which is incredibly important.
- Remember to use the `task` tool to silo independent tasks within a multi-part objective.
- You should use the `task` tool whenever you have a complex task that will take multiple steps, and is independent from other tasks that the agent needs to complete. These agents are highly competent and efficient."""  # noqa: E501


DEFAULT_GENERAL_PURPOSE_DESCRIPTION = "General-purpose agent for researching complex questions, searching for files and content, and executing multi-step tasks. When you are searching for a keyword or file and are not confident that you will find the right match in the first few tries use this agent to perform the search for you. This agent has access to all tools as the main agent."  # noqa: E501

# Base spec for general-purpose subagent (caller adds model, tools, middleware)
GENERAL_PURPOSE_SUBAGENT: SubAgent = {
    "name": "general-purpose",
    "description": DEFAULT_GENERAL_PURPOSE_DESCRIPTION,
    "system_prompt": DEFAULT_SUBAGENT_PROMPT,
}


class _SubagentSpec(TypedDict):
    """Internal spec for building the task tool."""

    name: str
    description: str
    runnable: Runnable

"""旧版subagent加载函数"""
def _get_subagents_legacy(
    *,
    default_model: str | BaseChatModel,
    default_tools: Sequence[BaseTool | Callable | dict[str, Any]],
    default_middleware: list[AgentMiddleware] | None,
    default_interrupt_on: dict[str, bool | InterruptOnConfig] | None,
    subagents: list[SubAgent | CompiledSubAgent],
    general_purpose_agent: bool,
) -> list[_SubagentSpec]:
    """Create subagent instances from specifications.

    Args:
        default_model: Default model for subagents that don't specify one.
        default_tools: Default tools for subagents that don't specify tools.
        default_middleware: Middleware to apply to all subagents. If `None`,
            no default middleware is applied.
        default_interrupt_on: The tool configs to use for the default general-purpose subagent. These
            are also the fallback for any subagents that don't specify their own tool configs.
        subagents: List of agent specifications or pre-compiled agents.
        general_purpose_agent: Whether to include a general-purpose subagent.

    Returns:
        List of subagent specs containing name, description, and runnable.
    """
    # Use empty list if None (no default middleware)
    default_subagent_middleware = default_middleware or []

    specs: list[_SubagentSpec] = []

    # Create general-purpose agent if enabled
    if general_purpose_agent:
        general_purpose_middleware = [*default_subagent_middleware]
        if default_interrupt_on:
            general_purpose_middleware.append(HumanInTheLoopMiddleware(interrupt_on=default_interrupt_on))
        general_purpose_subagent = create_agent(
            default_model,
            system_prompt=DEFAULT_SUBAGENT_PROMPT,
            tools=default_tools,
            middleware=general_purpose_middleware,
            name="general-purpose",
        )
        specs.append(
            {
                "name": "general-purpose",
                "description": DEFAULT_GENERAL_PURPOSE_DESCRIPTION,
                "runnable": general_purpose_subagent,
            }
        )

    # Process custom subagents
    for agent_ in subagents:
        if "runnable" in agent_:
            custom_agent = cast("CompiledSubAgent", agent_)
            specs.append(
                {
                    "name": custom_agent["name"],
                    "description": custom_agent["description"],
                    "runnable": custom_agent["runnable"],
                }
            )
            continue
        _tools = agent_.get("tools", list(default_tools))

        subagent_model = agent_.get("model", default_model)

        _middleware = [*default_subagent_middleware, *agent_["middleware"]] if "middleware" in agent_ else [*default_subagent_middleware]

        interrupt_on = agent_.get("interrupt_on", default_interrupt_on)
        if interrupt_on:
            _middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))

        specs.append(
            {
                "name": agent_["name"],
                "description": agent_["description"],
                "runnable": create_agent(
                    subagent_model,
                    system_prompt=agent_["system_prompt"],
                    tools=_tools,
                    middleware=_middleware,
                    name=agent_["name"],
                ),
            }
        )

    return specs

"""最后返回的是`task`结构化tool"""
def _build_task_tool(  # noqa: C901
    subagents: list[_SubagentSpec],
    task_description: str | None = None,
) -> BaseTool:
    """Create a task tool from pre-built subagent graphs.

    This is the shared implementation used by both the legacy API and new API.

    Args:
        subagents: List of subagent specs containing name, description, and runnable.
        task_description: Custom description for the task tool. If `None`,
            uses default template. Supports `{available_agents}` placeholder.

    Returns:
        A StructuredTool that can invoke subagents by type.
    """
    # Build the graphs dict and descriptions from the unified spec list
    subagent_graphs: dict[str, Runnable] = {spec["name"]: spec["runnable"] for spec in subagents}
    subagent_description_str = "\n".join(f"- {s['name']}: {s['description']}" for s in subagents)

    # Use custom description if provided, otherwise use default template
    if task_description is None:
        description = TASK_TOOL_DESCRIPTION.format(available_agents=subagent_description_str)
    elif "{available_agents}" in task_description:
        description = task_description.format(available_agents=subagent_description_str)
    else:
        description = task_description

    def _return_command_with_state_update(result: dict, tool_call_id: str, *, content_override: str | None = None) -> Command:
        # Validate that the result contains a 'messages' key
        if "messages" not in result:
            error_msg = (
                "CompiledSubAgent must return a state containing a 'messages' key. "
                "Custom StateGraphs used with CompiledSubAgent should include 'messages' "
                "in their state schema to communicate results back to the main agent."
            )
            raise ValueError(error_msg)

        state_update = {k: v for k, v in result.items() if k not in _EXCLUDED_STATE_KEYS}
        # 优先使用 content_override（经 Pydantic 填充默认值后的完整 JSON）
        # 回退到原始 LLM 输出文本
        if content_override is not None:
            message_text = content_override
        else:
            message_text = result["messages"][-1].text.rstrip() if result["messages"][-1].text else ""
        return Command(
            update={
                **state_update,
                "messages": [ToolMessage(message_text, tool_call_id=tool_call_id)],
            }
        )

    def _validate_and_prepare_state(subagent_type: str, description: str, runtime: ToolRuntime) -> tuple[Runnable, dict]:
        """Prepare state for invocation."""
        subagent = subagent_graphs[subagent_type]
        # Create a new state dict to avoid mutating the original
        subagent_state = {k: v for k, v in runtime.state.items() if k not in _EXCLUDED_STATE_KEYS}
        # Inject relevant evidence from MasterAgent state into the task description
        enriched_description = _enrich_task_description(subagent_type, description, subagent_state)
        subagent_state["messages"] = [HumanMessage(content=enriched_description)]
        return subagent, subagent_state

    def task(
        description: Annotated[
            str,
            "A detailed description of the task for the subagent to perform autonomously. Include all necessary context and specify the expected output format.",  # noqa: E501
        ],
        subagent_type: Annotated[str, "The type of subagent to use. Must be one of the available agent types listed in the tool description."],
        runtime: ToolRuntime,
    ) -> str | Command:
        if subagent_type not in subagent_graphs:
            allowed_types = ", ".join([f"`{k}`" for k in subagent_graphs])
            return f"We cannot invoke subagent {subagent_type} because it does not exist, the only allowed types are {allowed_types}"
        subagent, subagent_state = _validate_and_prepare_state(subagent_type, description, runtime)

        # SSE 进度事件：子智能体开始执行
        try:
            writer = get_stream_writer()
            writer({
                "status": "subagent_progress",
                "event": "started",
                "subagent_type": subagent_type,
                "description": description,
            })
        except Exception:
            pass

        max_retries = 2
        result = None
        total_tool_calls = 0
        for attempt in range(max_retries):
            result = subagent.invoke(subagent_state)
            message_text = result["messages"][-1].text.rstrip() if result["messages"][-1].text else ""
            # 统计本轮工具调用次数（含跨重试累计）
            attempt_calls = sum(
                len(msg.tool_calls) if hasattr(msg, 'tool_calls') and msg.tool_calls else 0
                for msg in result.get("messages", [])
            )
            total_tool_calls += attempt_calls
            is_valid, validated_or_error = _validate_output(subagent_type, message_text)
            if is_valid:
                message_text = validated_or_error  # 使用 Pydantic 填充默认值后的完整 JSON
                break
            logging.warning(f"[SubAgent] {subagent_type} 输出格式验证失败（第{attempt + 1}次），正在重试...")
            if attempt < max_retries - 1:
                # SSE 进度事件：重试
                try:
                    writer = get_stream_writer()
                    writer({
                        "status": "subagent_progress",
                        "event": "retry",
                        "subagent_type": subagent_type,
                        "attempt": attempt + 2,
                    })
                except Exception:
                    pass
                # 保留第一轮完整消息历史（含工具调用结果），仅追加格式化指令
                previous_messages = list(result["messages"])
                previous_messages.append(
                    HumanMessage(content=(
                        f"[系统] 输出格式校验未通过，请直接修正 JSON 格式。"
                        f"不要重新调用任何工具，基于已有数据重新输出即可。\n{validated_or_error}"
                    ))
                )
                subagent_state = {k: v for k, v in runtime.state.items() if k not in _EXCLUDED_STATE_KEYS}
                subagent_state["messages"] = previous_messages

        if total_tool_calls > 20:
            logging.warning(f"[SubAgent] {subagent_type} 本轮调用工具{total_tool_calls}次（含{attempt+1}次重试），频率偏高请关注")
        if not runtime.tool_call_id:
            value_error_msg = "Tool call ID is required for subagent invocation"
            raise ValueError(value_error_msg)

        # SSE 进度事件：子智能体执行完成
        try:
            writer = get_stream_writer()
            writer({
                "status": "subagent_progress",
                "event": "completed",
                "subagent_type": subagent_type,
                "tool_calls": total_tool_calls,
            })
        except Exception:
            pass

        return _return_command_with_state_update(result, runtime.tool_call_id, content_override=message_text)

    async def atask(
        description: Annotated[
            str,
            "A detailed description of the task for the subagent to perform autonomously. Include all necessary context and specify the expected output format.",  # noqa: E501
        ],
        subagent_type: Annotated[str, "The type of subagent to use. Must be one of the available agent types listed in the tool description."],
        runtime: ToolRuntime,
    ) -> str | Command:
        if subagent_type not in subagent_graphs:
            allowed_types = ", ".join([f"`{k}`" for k in subagent_graphs])
            return f"We cannot invoke subagent {subagent_type} because it does not exist, the only allowed types are {allowed_types}"

        try:
            subagent, subagent_state = _validate_and_prepare_state(subagent_type, description, runtime)
            logging.info(f"\n{'='*50}\n[MASTER AGENT 调度指令]\n目标子智能体: {subagent_type}\n任务描述: {description}\n{'='*50}\n")

            # SSE 进度事件：子智能体开始执行
            try:
                writer = get_stream_writer()
                writer({
                    "status": "subagent_progress",
                    "event": "started",
                    "subagent_type": subagent_type,
                    "description": description,
                })
            except Exception:
                pass

            max_retries = 2
            result = None
            total_tool_calls = 0
            for attempt in range(max_retries):
                result = await subagent.ainvoke(subagent_state)
                message_text = result["messages"][-1].text.rstrip() if result["messages"][-1].text else ""
                # 统计本轮工具调用次数（含跨重试累计）
                attempt_calls = sum(
                    len(msg.tool_calls) if hasattr(msg, 'tool_calls') and msg.tool_calls else 0
                    for msg in result.get("messages", [])
                )
                total_tool_calls += attempt_calls
                is_valid, validated_or_error = _validate_output(subagent_type, message_text)
                if is_valid:
                    message_text = validated_or_error  # 使用 Pydantic 填充默认值后的完整 JSON
                    break
                logging.warning(f"[SubAgent] {subagent_type} 输出格式验证失败（第{attempt + 1}次），正在重试...")
                if attempt < max_retries - 1:
                    # SSE 进度事件：重试
                    try:
                        writer = get_stream_writer()
                        writer({
                            "status": "subagent_progress",
                            "event": "retry",
                            "subagent_type": subagent_type,
                            "attempt": attempt + 2,
                        })
                    except Exception:
                        pass
                    # 保留第一轮完整消息历史（含工具调用结果），仅追加格式化指令
                    # 避免重试时重复执行搜索/详情等耗时工具
                    previous_messages = list(result["messages"])
                    previous_messages.append(
                        HumanMessage(content=(
                            f"[系统] 输出格式校验未通过，请直接修正 JSON 格式。"
                            f"不要重新调用任何工具，基于已有数据重新输出即可。\n{validated_or_error}"
                        ))
                    )
                    subagent_state = {k: v for k, v in runtime.state.items() if k not in _EXCLUDED_STATE_KEYS}
                    subagent_state["messages"] = previous_messages
        except Exception as e:
            err_msg = f"[SubAgent] {subagent_type} 执行失败: {e}"
            logging.error(err_msg, exc_info=False)
            return f"子智能体 {subagent_type} 执行时遇到错误: {e}。请根据已有信息继续处理，或调整策略后重试。"

        if total_tool_calls > 20:
            logging.warning(f"[SubAgent] {subagent_type} 本轮调用工具{total_tool_calls}次（含{attempt+1}次重试），频率偏高请关注")
        if not runtime.tool_call_id:
            value_error_msg = "Tool call ID is required for subagent invocation"
            raise ValueError(value_error_msg)

        # SSE 进度事件：子智能体执行完成
        try:
            writer = get_stream_writer()
            writer({
                "status": "subagent_progress",
                "event": "completed",
                "subagent_type": subagent_type,
                "tool_calls": total_tool_calls,
            })
        except Exception:
            pass

        return _return_command_with_state_update(result, runtime.tool_call_id, content_override=message_text)

    return StructuredTool.from_function(
        name="task",
        func=task,
        coroutine=atask,
        description=description,
    )


class _DeprecatedKwargs(TypedDict, total=False):
    """TypedDict for deprecated SubAgentMiddleware keyword arguments.

    These arguments are deprecated and will be removed in version 0.5.0.
    Use `backend` and fully-specified `subagents` instead.
    """


class SubAgentMiddleware(AgentMiddleware[Any, ContextT, ResponseT]):
    """Middleware for providing subagents to an agent via a `task` tool.

    This middleware adds a `task` tool to the agent that can be used to invoke subagents.
    Subagents are useful for handling complex tasks that require multiple steps, or tasks
    that require a lot of context to resolve.

    A chief benefit of subagents is that they can handle multi-step tasks, and then return
    a clean, concise response to the main agent.

    Subagents are also great for different domains of expertise that require a narrower
    subset of tools and focus.

    Args:
        backend: Backend for file operations and execution. Required for the new API.
        subagents: List of fully-specified subagent configs. Each SubAgent
            must specify `model` and `tools`. Optional `interrupt_on` on
            individual subagents is respected.
        system_prompt: Instructions appended to main agent's system prompt
            about how to use the task tool.
        task_description: Custom description for the task tool.

    Example:
        ```python
        from deepagents.middleware import SubAgentMiddleware
        from langchain.agents import create_agent

        agent = create_agent(
            "openai:gpt-4o",
            middleware=[
                SubAgentMiddleware(
                    backend=my_backend,
                    subagents=[
                        {
                            "name": "researcher",
                            "description": "Research agent",
                            "system_prompt": "You are a researcher.",
                            "model": "openai:gpt-4o",
                            "tools": [search_tool],
                        }
                    ],
                )
            ],
        )
        ```

    .. deprecated::
        The following arguments are deprecated and will be removed in version 0.5.0:
        `default_model`, `default_tools`, `default_middleware`,
        `default_interrupt_on`, `general_purpose_agent`. Use `backend` and `subagents` instead.
    """

    # Valid deprecated kwarg names for runtime validation
    _VALID_DEPRECATED_KWARGS = frozenset(
        {
            "default_model",
            "default_tools",
            "default_middleware",
            "default_interrupt_on",
            "general_purpose_agent",
        }
    )

    def __init__(
        self,
        *,
        backend: BackendProtocol | BackendFactory | None = None,
        subagents: list[SubAgent | CompiledSubAgent] | None = None,
        system_prompt: str | None = TASK_SYSTEM_PROMPT,
        task_description: str | None = None,
        **deprecated_kwargs: Unpack[_DeprecatedKwargs],
    ) -> None:
        """Initialize the `SubAgentMiddleware`."""
        super().__init__()

        # Validate that only known deprecated kwargs are passed
        unknown_kwargs = set(deprecated_kwargs.keys()) - self._VALID_DEPRECATED_KWARGS
        if unknown_kwargs:
            msg = f"SubAgentMiddleware got unexpected keyword argument(s): {', '.join(sorted(unknown_kwargs))}"
            raise TypeError(msg)

        # Handle deprecated kwargs for backward compatibility
        default_model = deprecated_kwargs.get("default_model")
        default_tools = deprecated_kwargs.get("default_tools")
        default_middleware = deprecated_kwargs.get("default_middleware")
        default_interrupt_on = deprecated_kwargs.get("default_interrupt_on")
        # general_purpose_agent defaults to True if not specified
        general_purpose_agent = deprecated_kwargs.get("general_purpose_agent", True)

        # Warn about any deprecated kwargs that were provided
        provided_deprecated = [key for key in deprecated_kwargs if key != "general_purpose_agent"]
        if "general_purpose_agent" in deprecated_kwargs and not general_purpose_agent:
            provided_deprecated.append("general_purpose_agent")

        if provided_deprecated:
            warnings.warn(
                f"The following SubAgentMiddleware arguments are deprecated and will be removed "
                f"in version 0.5.0: {', '.join(provided_deprecated)}. "
                f"Use `backend` and fully-specified `subagents` instead.",
                DeprecationWarning,
                stacklevel=2,
            )

        # Detect which API is being used
        using_new_api = backend is not None
        using_old_api = default_model is not None

        if using_old_api and not using_new_api:
            # Legacy API - build subagents from deprecated args
            subagent_specs = _get_subagents_legacy(
                default_model=default_model,  # ty: ignore[invalid-argument-type]
                default_tools=default_tools or [],
                default_middleware=default_middleware,
                default_interrupt_on=default_interrupt_on,
                subagents=subagents or [],
                general_purpose_agent=general_purpose_agent,
            )
        elif using_new_api:
            if not subagents:
                msg = "At least one subagent must be specified when using the new API"
                raise ValueError(msg)
            self._backend = backend
            self._subagents = subagents
            subagent_specs = self._get_subagents()
        else:
            msg = "SubAgentMiddleware requires either `backend` (new API) or `default_model` (deprecated API)"
            raise ValueError(msg)

        task_tool = _build_task_tool(subagent_specs, task_description)

        # Build system prompt with available agents
        if system_prompt and subagent_specs:
            agents_desc = "\n".join(f"- {s['name']}: {s['description']}" for s in subagent_specs)
            self.system_prompt = system_prompt + "\n\nAvailable subagent types:\n" + agents_desc
        else:
            self.system_prompt = system_prompt

        self.tools = [task_tool]

    """获取已编译的可执行智能体字典"""
    def _get_subagents(self) -> list[_SubagentSpec]:
        """Create runnable agents from specs.

        Returns:
            List of subagent specs with name, description, and runnable.
        """
        specs: list[_SubagentSpec] = []

        for spec in self._subagents:
            if "runnable" in spec:
                # CompiledSubAgent - use as-is
                compiled = cast("CompiledSubAgent", spec)
                specs.append({"name": compiled["name"], "description": compiled["description"], "runnable": compiled["runnable"]})
                continue

            # SubAgent - validate required fields
            if "model" not in spec:
                msg = f"SubAgent '{spec['name']}' must specify 'model'"
                raise ValueError(msg)
            if "tools" not in spec:
                msg = f"SubAgent '{spec['name']}' must specify 'tools'"
                raise ValueError(msg)

            # Resolve model if string
            model = spec["model"]
            if isinstance(model, str):
                model = init_chat_model(model)

            # Use middleware as provided (caller is responsible for building full stack)
            middleware: list[AgentMiddleware] = list(spec.get("middleware", []))

            interrupt_on = spec.get("interrupt_on")
            if interrupt_on:
                middleware.append(HumanInTheLoopMiddleware(interrupt_on=interrupt_on))

            specs.append(
                {
                    "name": spec["name"],
                    "description": spec["description"],
                    "runnable": create_agent(
                        model,
                        system_prompt=spec["system_prompt"],
                        tools=spec["tools"],
                        middleware=middleware,
                        name=spec["name"],
                    ),
                }
            )

        return specs

    def wrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], ModelResponse[ResponseT]],
    ) -> ModelResponse[ResponseT]:
        """Update the system message to include instructions on using subagents."""
        if self.system_prompt is not None:
            new_system_message = append_to_system_message(request.system_message, self.system_prompt)
            return handler(request.override(system_message=new_system_message))
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest[ContextT],
        handler: Callable[[ModelRequest[ContextT]], Awaitable[ModelResponse[ResponseT]]],
    ) -> ModelResponse[ResponseT]:
        """(async) Update the system message to include instructions on using subagents."""
        if self.system_prompt is not None:
            new_system_message = append_to_system_message(request.system_message, self.system_prompt)
            return await handler(request.override(system_message=new_system_message))
        return await handler(request)
