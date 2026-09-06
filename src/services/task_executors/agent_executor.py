"""
Agent 定时任务执行器

每个定时任务是一次完整的 LangGraph Agent 对话——和用户聊天完全一样，
只是触发者不是人而是时钟。

task_params 结构:
    {
        "prompt": "帮我搜今天的数码热榜并总结推荐",
        "user_id": "xxx",                     # 可选，默认用 task.user_id
    }

与 Hermes cron job 的对比:
    - 不复用 skill 注入（SubAgent 已经承担了领域专家的角色）
    - 不复用多平台投递（结果存 DB，用户下次打开前端拉取）
    - 不做 cronjob 工具递归禁用（Master 本身不会创建定时任务）
"""

import logging
import uuid
from datetime import datetime, timezone

from langchain_core.messages import HumanMessage, AIMessage

from src.agents import agent_manager
from src.storage.postgres.models_business import TaskRecord

logger = logging.getLogger(__name__)


async def execute(task: TaskRecord) -> dict:
    """
    执行一次 Agent 定时任务。

    1. 用 task_params.prompt 构建 HumanMessage
    2. 本地 invoke Agent 图（非流式，无人接收 SSE）
    3. 提取最终 AI 回复
    4. 返回结构化摘要
    """
    params = task.task_params or {}
    prompt = params.get("prompt", "")
    user_id = params.get("user_id", task.user_id)

    if not prompt:
        return {"error": "缺少 prompt 参数"}

    # ── 获取 MasterAgent 实例 ──
    agent = agent_manager.get_agent("MasterAgent")
    if agent is None:
        return {"error": "MasterAgent 实例不存在，请确认已注册"}

    graph = await agent.get_graph()

    # ── 会话隔离：每次触发使用全新的 thread_id ──
    thread_id = f"cron_{task.id}_{uuid.uuid4().hex[:8]}"

    messages = [HumanMessage(content=prompt)]

    # ── 构建上下文（与 chat_stream_service 对齐）──
    context = agent.context_schema()
    context.update({
        "user_id": user_id,
        "thread_id": thread_id,
    })

    input_config = {
        "configurable": {"thread_id": thread_id, "user_id": user_id},
        "recursion_limit": 100,
    }

    logger.info(
        f"[AgentExecutor] 开始执行任务 {task.id}: "
        f"prompt={prompt[:80]}..., thread_id={thread_id}"
    )

    # ── 非流式调用：后台任务无需 SSE 推送 ──
    try:
        final_state = await graph.ainvoke(
            input={"messages": messages},
            context=context,
            config=input_config,
        )
    except Exception as exc:
        logger.error(f"[AgentExecutor] Agent 执行失败: {exc}", exc_info=True)
        return {
            "status": "failed",
            "error": str(exc),
            "thread_id": thread_id,
            "executed_at": datetime.now(timezone.utc).isoformat(),
        }

    # ── 提取最终 AI 回复 ──
    final_messages = final_state.get("messages", [])
    response_text = ""
    tool_calls_count = 0

    for msg in final_messages:
        if hasattr(msg, "tool_calls") and msg.tool_calls:
            tool_calls_count += len(msg.tool_calls)

    # 从后往前找最后一条 AIMessage
    for msg in reversed(final_messages):
        if isinstance(msg, AIMessage) and msg.content:
            content = msg.content
            response_text = content if isinstance(content, str) else str(content)
            break

    logger.info(
        f"[AgentExecutor] 任务 {task.id} 执行完成: "
        f"messages={len(final_messages)}, tool_calls={tool_calls_count}, "
        f"response_len={len(response_text)}"
    )

    return {
        "status": "ok",
        "prompt": prompt,
        "thread_id": thread_id,
        "response": response_text[:3000],
        "response_length": len(response_text),
        "total_messages": len(final_messages),
        "tool_calls": tool_calls_count,
        "executed_at": datetime.now(timezone.utc).isoformat(),
    }
