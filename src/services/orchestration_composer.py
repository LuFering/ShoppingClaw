"""
编排轨迹合成器 —— 把「真实 LLM 执行」映射成前端契约 v1.0 的 orchestration 载荷。

═══════════════════════════════════════════════════════════════════════════
为什么需要这一层（对照 Yuxi 的实现）
═══════════════════════════════════════════════════════════════════════════

Yuxi 的做法（`backend/package/yuxi/services/chat_service.py`）值得照抄的是它
**不新增协议**，而是加了一个**翻译层**：

    LangGraph 原始事件  →  _message_payload_yuxi_events()  →  yuxi 自有事件
      (AIMessageChunk)      (message_delta / tool_call)      (stream_event)

我们这边同样有翻译层（`sse_adapter.legacy_chunk_to_events`），把旧 chunk 翻成
EventType。`orchestrate` / `task` 卡属于**契约层虚构的编排动作**，在 registry 里
没有对应真实工具 —— 所以不能靠 LLM 产出，必须由 runtime **合成**。

本模块就是合成器。它不做任何 LLM 调用、不碰业务数据，只做两件事：
  1. 维护「当前气泡 id」——即 Yuxi 的 `_stream_message_id` 对应物；
  2. 按 ORCHESTRATION_REVEAL_STEPS 顺序，把编排决策**逐段**吐出去。

═══════════════════════════════════════════════════════════════════════════
三条硬规则（踩过坑，写在这里当护栏）
═══════════════════════════════════════════════════════════════════════════

规则 1：气泡 id 只在「即将发出 tool_start」时推进。
        纯文本段一律复用当前 id。
        —— 反例 A：全部文本共用一个 id → 被拼成一大段。
        —— 反例 B：每句一个新 id → 开篇正文与紧随口播之间没有状态块，切成空对空气泡。

规则 2：渐进显形靠「同 tool_call_id 反复发 tool_start」，不是新事件类型。
        未显形的分区必须下发**空值**（None / [] / ""），不能省略键。
        省略键会让下游分不清「还没到」和「本就没有」。

规则 3：`task` 是容器型，它的 tool_start 允许被子智能体内部工具事件夹断；
        `orchestrate` 是叶子型，要求同 id 连续。
        —— 但渐进显形会不断重置计时，所以 duration 要单独记（见 _orch_started_at）。

═══════════════════════════════════════════════════════════════════════════
一条设计红线：只呈现「做了什么」，不呈现「为什么不做什么」（2026-09-18）
═══════════════════════════════════════════════════════════════════════════

本模块**不做意图分诊、不做置信度判定**。

原因：用户实测发现，让模型先跑一遍意图判定再行动，效果**不如**让它直接理解语境。
判定环节既会误判，又会把内部决策语气泄露进对话 —— 典型症状是用户只说「你好」，
却收到「置信度太低，派出去只会白跑」这样一段系统日志口吻的自述。

所以：
  · 「要不要派子智能体」完全由**模型自己决定**。它发出 `task` 就派，不发就不派。
  · runtime 不做阈值判定、不做关键词匹配、不猜置信度、不展示判定结论。
  · 编排卡只在**已经发生派遣**时才出现（由 `task` 触发合成），
    因此它天然是「执行事实的记录」，不需要论证自己该不该存在。
  · `decision` 字段的措辞必须是「在做什么」的陈述句。它会被模型看见，
    所以绝不能用「未派遣」「白跑」这类辩解/否定式表达，否则会被学去当对话说。

契约真源：web-v2/src/agent/mainAgentContracts.js
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Iterable

_log = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════
# 契约常量 —— 必须与 mainAgentContracts.js 逐字一致
# ═══════════════════════════════════════════════════════════════════════

CONTRACT_VERSION = 1

#: 渐进显形顺序。前端 OrchestrateTool.vue 的 REVEAL_ORDER 是同一条。
#:
#: ⚠️ 曾经的第一档是 `intent`（意图分诊 + 置信度），2026-09-18 已移除。
#: 原因（用户实测结论）：**让模型直接理解语境，好过先跑一遍判定**。
#: 置信度分诊在实际使用中不好用 —— 它既容易误判，又会把
#: 「置信度 0.31 / 派出去只会白跑」这类**内部决策语气**泄露到对话里，
#: 用户只是在打招呼，却读到一段系统日志口吻的自述。
#: 现在：**要不要派子智能体，完全由模型自己决定**（它发 task 就派，
#: 不发就不派），runtime 不再做任何阈值/关键词判定，也不展示判定结论。
ORCHESTRATION_REVEAL_STEPS: tuple[str, ...] = (
    "skills",
    "rag",
    "mcp",
    "dispatch",
    "decision",
)

#: 前端 TOOL_RENDERERS 的 key —— tool_name 必须一字不差，否则卡片降级成通用样式。
TOOL_ORCHESTRATE = "orchestrate"
TOOL_TASK = "task"
TOOL_ASK_USER = "ask_user"

#: 购后的业务 = 购物档案（归档 / 阶段 / 提醒 / 复盘），不触碰订单·物流·售后·支付。
ARCHIVE_ONLY_NOTE = "购后的业务 = 购物档案（归档/阶段/提醒/复盘），不触碰订单·物流·售后·支付"

#: 后端 subagents.yaml 的 slug → 前端展示名。
#: 4 个后端 slug 对 2 个前端名字，是多对一 —— 映射放后端，前端不该写这张表。
SUBAGENT_DISPLAY_NAME: dict[str, str] = {
    "researcher": "购前助手",
    "analyst": "购前助手",
    "critic": "购前助手",
    "memory_manager": "购后助手",
    "pre_purchase": "购前助手",
    "post_purchase": "购后助手",
}


def display_name(slug: str | None) -> str:
    """把后端 slug 翻成前端展示名；未知 slug 原样返回。"""
    if not slug:
        return "子智能体"
    return SUBAGENT_DISPLAY_NAME.get(str(slug), str(slug))


# ═══════════════════════════════════════════════════════════════════════
# 气泡 id 分配器 —— Yuxi `_stream_message_id` 的对应物
# ═══════════════════════════════════════════════════════════════════════


class Narrator:
    """气泡 id 分配器。

    Yuxi 的 `_stream_message_id(protocol_message_ids, key, preferred)` 用
    `(thread_id, run_id)` 做 key 缓存 id —— 同一个 run 里所有 chunk 共享一个
    message_id，run 变了才换。这里用等价的思路，但把「何时换」的判断权交给
    调用方：**只在即将发 tool_start 时调 `next()`**。

    用法::

        n = Narrator("round-1")
        emit_text(n.current())          # 正文段，复用当前 id
        emit_tool_start(n.next())       # 推进 id，状态块挂到新气泡
        emit_text(n.current())          # 新一段正文，跟着新气泡
    """

    __slots__ = ("base", "_n", "_current")

    def __init__(self, base: str = "round-1") -> None:
        self.base = base
        self._n = 0
        # 初始就有一个「当前气泡」，让开篇正文有归属。
        self._n = 1
        self._current = f"{self.base}-s{self._n}"

    def current(self) -> str:
        """当前气泡 id —— 文本段用它。"""
        return self._current

    def next(self) -> str:
        """推进到下一个气泡 id —— **只在即将发 tool_start 时调用**。"""
        self._n += 1
        self._current = f"{self.base}-s{self._n}"
        return self._current


# ═══════════════════════════════════════════════════════════════════════
# 编排轨迹 —— 契约 orchestration 载荷的构造与分段
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class OrchestrationTrace:
    """契约 v1 的 `orchestration` 载荷 —— **只描述执行事实**。

    运行中与已完成**结构完全一致**，只差 `status` —— 所以前端在 running
    时就能整卡渲染，不需要等 completed。

    ⚠️ 这里刻意**没有** `intent` / `confidence` 字段（2026-09-18 移除）。
    本卡片的职责是「如实呈现这一步做了什么」：
      用了哪些 Skill、查了哪些 RAG、调了哪些 MCP、派了谁、结论是什么。
    它不是「我为什么决定不派」的答辩书 —— 那种内部推理不该给用户看，
    更不该被模型学去当成对话内容说出口。
    """

    skills: list[dict[str, Any]] = field(default_factory=list)
    rag: list[dict[str, Any]] = field(default_factory=list)
    mcp: list[dict[str, Any]] = field(default_factory=list)
    dispatch: list[dict[str, Any]] = field(default_factory=list)
    decision: str = ""
    guardrails: dict[str, Any] = field(default_factory=dict)

    def _guardrails(self) -> dict[str, Any]:
        base = {"touched_business_data": False, "note": ARCHIVE_ONLY_NOTE}
        base.update(self.guardrails or {})
        return base

    def build(self, status: str = "running", up_to: int | None = None) -> dict[str, Any]:
        """构造下发给前端的一份轨迹。

        Args:
            status: ``running`` / ``completed`` / ``failed``
            up_to:  已显形分区数（0..5）。``None`` = 全部显形（向后兼容）。

        未显形的分区下发**空值**而非省略键 —— 见模块 docstring 规则 2。
        """
        full: dict[str, Any] = {
            "version": CONTRACT_VERSION,
            "status": status,
            "skills": list(self.skills),
            "rag": list(self.rag),
            "mcp": list(self.mcp),
            "dispatch": list(self.dispatch),
            "decision": self.decision,
            "guardrails": self._guardrails(),
        }
        total = len(ORCHESTRATION_REVEAL_STEPS)
        if up_to is None:
            return {**full, "step": total}

        n = max(0, min(int(up_to), total))
        shown = set(ORCHESTRATION_REVEAL_STEPS[:n])

        def has(key: str) -> bool:
            return key in shown

        return {
            **full,
            "step": n,
            "skills": full["skills"] if has("skills") else [],
            "rag": full["rag"] if has("rag") else [],
            "mcp": full["mcp"] if has("mcp") else [],
            "dispatch": full["dispatch"] if has("dispatch") else [],
            "decision": full["decision"] if has("decision") else "",
        }


# ═══════════════════════════════════════════════════════════════════════
# 子智能体运行态 —— 契约 subagent_run 载荷
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class SubagentRun:
    """契约的 `subagent_run` 载荷（`task` 卡的肉体）。

    与 OrchestrationTrace 同样是「运行中即可整卡渲染」的设计。
    `plannedTools` 先亮出来（让用户看见打算做什么），`tools` 随执行追加。
    """

    slug: str
    task: str = ""
    status: str = "running"
    # 关联的 tool_call_id。默认空串由 Orchestrator.start_task 填合成 id；
    # 当 runtime 用真实 langchain tool_call_id 覆盖时必须同步改这里，
    # 否则前端拿着 subagent_run.call_id 找不到对应的那张 task 卡。
    call_id: str = ""
    skills: list[dict[str, Any]] = field(default_factory=list)
    rag: list[dict[str, Any]] = field(default_factory=list)
    tools: list[dict[str, Any]] = field(default_factory=list)
    planned_tools: list[dict[str, Any]] = field(default_factory=list)

    def build(self) -> dict[str, Any]:
        # ⚠️ 字段对齐前端契约（mock 阶段 TaskTool.vue 的真实消费字段）：
        #   TaskTool 第一行读 `subagentRun.subagent_name`；mock 则靠
        #   `arguments.subagent`（label）兜底。二者任一缺失都会让卡片回退成
        #   「调用子智能体」这种工具名，所以这里两个都给上，与 mock 完全等价。
        _label = display_name(self.slug)
        return {
            "slug": self.slug,
            "subagent_name": _label,
            "display_name": _label,
            "task": self.task,
            "status": self.status,
            "call_id": self.call_id,
            "skills": [dict(x) for x in self.skills],
            "rag": [dict(x) for x in self.rag],
            "tools": [dict(x) for x in self.tools],
            "plannedTools": [dict(x) for x in self.planned_tools],
        }

    def mark_rag_done(self, name: str) -> None:
        for item in self.rag:
            if item.get("name") == name:
                item["done"] = True
                return

    def add_tool(
        self,
        name: str,
        detail: str = "",
        *,
        duration_ms: int | None = None,
        status: str = "done",
        call_id: str = "",
    ) -> None:
        """记录一个子智能体内部真实执行过的工具，并把同名 plannedTool 标 done。

        同一 `call_id` 重复上报时**原地更新**，不重复追加 —— sse_monitor 会对
        同一个调用先发 tool_start 再发 tool_complete，两次都 append 的话
        卡片上就会同名出现两行。
        """
        target = None
        if call_id:
            for t in self.tools:
                if t.get("call_id") == call_id:
                    target = t
                    break
        if target is None:
            for t in self.tools:
                if t.get("name") == name and not t.get("done"):
                    target = t
                    break

        if target is not None:
            if detail:
                target["detail"] = detail
            target["done"] = status != "running"
            target["status"] = status
            if duration_ms is not None:
                target["duration_ms"] = duration_ms
            if call_id:
                target["call_id"] = call_id
        else:
            item = {"name": name, "detail": detail, "done": status != "running", "status": status}
            if duration_ms is not None:
                item["duration_ms"] = duration_ms
            if call_id:
                item["call_id"] = call_id
            self.tools.append(item)

        if status != "running":
            for p in self.planned_tools:
                if p.get("name") == name:
                    p["done"] = True
                    break

    def plan_tool(self, name: str, detail: str = "") -> None:
        self.planned_tools.append({"name": name, "detail": detail, "done": False})


# ═══════════════════════════════════════════════════════════════════════
# 事件构造 —— 全部走「旧 chunk 风格」，由 sse_adapter 翻译成 EventType
# ═══════════════════════════════════════════════════════════════════════


def _tool_chunk(
    *,
    tool_call_id: str,
    function: str,
    args: dict[str, Any] | None,
    status: str,
    message_id: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """构造一个 `status="thinking_process", event="tool_call"` 的旧 chunk。

    注意：这里**必须**走旧 chunk 风格，让 `sse_adapter.legacy_chunk_to_events`
    统一翻译。绕开 adapter 直接吐 EventType 会丢掉它做的字段归一化。
    """
    tool_call: dict[str, Any] = {
        "tool_call_id": tool_call_id,
        "function": function,
        "name": function,
        "args": args or {},
        "status": status,
        "message_id": message_id,
    }
    if extra:
        tool_call.update(extra)
    return {
        "status": "thinking_process",
        "event": "tool_call",
        "tool_call": tool_call,
    }


class Orchestrator:
    """一次对话轮次的编排合成器。

    挂在 `stream_agent_chat` 里，负责：
      · 维护 Narrator（气泡边界）
      · 合成 orchestrate 卡的渐进显形
      · 合成 task 卡（子智能体容器）
      · 合成 subagent_drill（展开/收起）

    它**不产生**任何业务数据，只负责「把已经发生的执行事实翻译成契约形态」。
    """

    def __init__(self, base_round: str = "round-1") -> None:
        self.narrator = Narrator(base_round)
        self._orch_id = f"orchestrate-{uuid.uuid4().hex[:12]}"
        # 渐进显形会反复发同 id tool_start，adapter 会重置 started_at，
        # 所以真实耗时必须自己记 —— 见模块 docstring 规则 3。
        self._orch_started_at: float = 0.0
        self._orch_emitted_step = 0
        self.tasks: dict[str, str] = {}  # slug -> task_call_id
        # real_call_id -> SubagentRun。供 task 完成时按 langchain 的
        # tool_call_id 反查是哪一个子智能体跑完了。
        self._task_runs: dict[str, SubagentRun] = {}

    # ── 气泡 ─────────────────────────────────────────────────────────

    def bubble(self) -> str:
        """当前气泡 id —— 文本段用它。"""
        return self.narrator.current()

    def advance(self) -> str:
        """推进气泡 —— **只在即将发 tool_start 时调用**。"""
        return self.narrator.next()

    # ── orchestrate 卡 ───────────────────────────────────────────────

    def orchestration_id(self) -> str:
        return self._orch_id

    def begin_orchestration(self) -> None:
        self._orch_started_at = time.time()
        self._orch_emitted_step = 0

    def reveal_step(
        self,
        trace: OrchestrationTrace,
        step: int,
        *,
        message_id: str | None = None,
    ) -> dict[str, Any]:
        """发出第 `step` 档显形（同 tool_call_id，前端就地覆盖 → 卡片长大）。

        幂等保护：同一档或回退档不重复发。
        """
        if step <= self._orch_emitted_step:
            step = self._orch_emitted_step + 1
        step = max(1, min(step, len(ORCHESTRATION_REVEAL_STEPS)))
        self._orch_emitted_step = step
        return _tool_chunk(
            tool_call_id=self._orch_id,
            function=TOOL_ORCHESTRATE,
            args={"decision": trace.decision},
            status="calling",
            message_id=message_id if message_id is not None else self.narrator.current(),
            extra={"orchestration": trace.build("running", up_to=step)},
        )

    def reveal_all(
        self, trace: OrchestrationTrace, *, message_id: str | None = None
    ) -> list[dict[str, Any]]:
        """一次性吐出全部分区（用于无法逐段推进的场景，如澄清）。"""
        self.begin_orchestration()
        return [
            self.reveal_step(trace, n, message_id=message_id)
            for n in range(1, len(ORCHESTRATION_REVEAL_STEPS) + 1)
        ]

    def complete_orchestration(
        self, trace: OrchestrationTrace, *, message_id: str | None = None
    ) -> dict[str, Any]:
        """编排卡收尾。

        ⚠️ `duration_ms` 用本类自己记的起点算 —— 不能用 adapter 的
        `active_tool_calls[id].started_at`，那会被渐进显形反复重置。
        """
        elapsed = 0
        if self._orch_started_at:
            elapsed = int((time.time() - self._orch_started_at) * 1000)
        final = trace.build("completed")
        return {
            "status": "thinking_process",
            "event": "tool_result",
            "tool_call": {
                "tool_call_id": self._orch_id,
                "function": TOOL_ORCHESTRATE,
                "name": TOOL_ORCHESTRATE,
                "args": {"decision": trace.decision},
                "content": json.dumps(
                    {"type": "orchestration", "orchestration": final},
                    ensure_ascii=False,
                ),
                "status": "completed",
                "duration_ms": elapsed,
                "message_id": message_id if message_id is not None else self.narrator.current(),
                "orchestration": final,
            },
        }

    # ── task 卡（子智能体容器）─────────────────────────────────────────

    def start_task(
        self,
        slug: str,
        task: str = "",
        *,
        skills: Iterable[str] = (),
        rag: Iterable[str] = (),
        planned_tools: Iterable[str] = (),
    ) -> tuple[str, SubagentRun, dict[str, Any]]:
        """开启一个子智能体卡片，返回 (tool_call_id, run, chunk)。

        `planned_tools` 建议填「打算执行」的工具名，让用户先看见计划。
        """
        call_id = f"task-{slug}-{uuid.uuid4().hex[:10]}"
        self.tasks[slug] = call_id
        run = SubagentRun(
            slug=slug,
            task=task,
            call_id=call_id,
            skills=[{"name": s} for s in skills],
            rag=[{"name": r, "detail": "", "done": False} for r in rag],
        )
        for t in planned_tools:
            run.plan_tool(t)
        self._task_runs[call_id] = run
        return call_id, run, self.task_chunk(call_id, run)

    def rebind_task_call_id(self, run: SubagentRun, real_call_id: str) -> None:
        """把合成 id 换成 runtime 真实观察到的 langchain tool_call_id。

        为什么要换：task 卡本身是 langchain 的 subagent_task 中间件发出的，
        它的 tool_call_id 由 langchain 生成（形如 `call_1d6c7b63...`），
        而我们合成 subagent_run 时先用了一个自造 id。两者不一致会导致
        前端按 tool_call_id 匹配卡片时对不上 —— 卡片长不出来。
        """
        old = run.call_id
        run.call_id = real_call_id
        if run.slug in self.tasks:
            self.tasks[run.slug] = real_call_id
        if old:
            self._task_runs.pop(old, None)
        self._task_runs[real_call_id] = run

    def task_chunk(self, call_id: str, run: SubagentRun) -> dict[str, Any]:
        """发一次 task 的 tool_start（同 id 反复发 = 卡片增量长大）。

        ⚠️ task 是**容器型**：它的 tool_start 会与子智能体内部工具事件交替出现，
        这是设计使然，不要为了「连续」去缓冲子工具事件。
        """
        return _tool_chunk(
            tool_call_id=call_id,
            function=TOOL_TASK,
            args={
                "subagent_type": run.slug,
                "subagent": display_name(run.slug),
                "description": run.task,
            },
            status="calling",
            message_id=self.narrator.current(),
            extra={"subagent_run": run.build()},
        )

    def complete_task(self, call_id: str, run: SubagentRun, duration_ms: int = 0) -> dict[str, Any]:
        run.status = "completed"
        final = run.build()
        return {
            "status": "thinking_process",
            "event": "tool_result",
                "tool_call": {
                    "tool_call_id": call_id,
                    "function": TOOL_TASK,
                    "name": TOOL_TASK,
                    "args": {
                        "subagent_type": run.slug,
                        "subagent": display_name(run.slug),
                        "description": run.task,
                    },
                    "content": json.dumps(
                        {"type": "subagent_run", "subagent_run": final}, ensure_ascii=False
                    ),
                    "status": "completed",
                    "duration_ms": duration_ms,
                    "message_id": self.narrator.current(),
                    "subagent_run": final,
                },
        }

    # ── subagent_drill ───────────────────────────────────────────────

    def drill(self, slug: str, action: str, description: str = "") -> dict[str, Any]:
        """合成 `subagent_drill`（expand / collapse）的**旧风格 chunk**。

        ⚠️ 这是**唯一需要新增的事件类型**（后端原先完全没有）。
        只写标志、不当场改展开态 —— 由 BaseToolCall 自己 watch，
        这样用户手动折叠过的卡片不会被强行重开。

        ⚠️ 返回的是带 `status` 判别位的 chunk（与其余方法一致），
        因为 `sse_adapter.legacy_chunk_to_events` 靠 `status` 路由。
        直接返回裸载荷会被 adapter 静默丢弃、产出 0 个事件 —— 踩过这个坑。
        """
        return {
            "status": "subagent_drill",
            "slug": slug,
            "action": action,
            "description": description,
            "message_id": self.narrator.current(),
        }


# ═══════════════════════════════════════════════════════════════════════
# 从「真实执行事实」推导编排轨迹
# ═══════════════════════════════════════════════════════════════════════
#
# 设计原则（2026-09-18 修订）：
#   **这里只记录「已经发生了什么」，不记录「我判断该不该做」。**
#   要不要派子智能体，完全由模型自己决定 —— 它发出 `task` 就派，
#   不发就不派。runtime 不做阈值判定、不做关键词匹配、不猜测置信度。
#   因此本层没有 intent / confidence 这类字段。


def new_trace(skills: Iterable[dict[str, Any]] = ()) -> OrchestrationTrace:
    """起一个空轨迹。可选直接给定 Skill 列表。"""
    return OrchestrationTrace(skills=[dict(s) for s in skills])


def fill_from_subagent_directory(
    trace: OrchestrationTrace,
    *,
    available_slugs: Iterable[str],
    selected: Iterable[tuple[str, str]] = (),
    tool_calls: Iterable[str] = (),
) -> OrchestrationTrace:
    """用「注册中心里的真实子智能体」填 skills / rag / dispatch。

    Args:
        available_slugs: 后端 subagents.yaml 里的全部 slug
        selected:        [(slug, task 描述)] —— 真正被派出去的那些

    RAG 项固定对应主智能体的路由库（见主智能体接口契约 v1.0）：
    subagent_directory / user_profile / archive_index

    ⚠️ 本函数只在**模型已经决定派遣**时被调用（卡片由 `task` 触发合成），
    所以这里不写任何「要不要派」的判断。`selected` 为空是异常情形，
    仍给出中性描述而不是辩解式文案。
    """
    # ═══ 三栏按**真实调用事实**填充（2026-09-22 重写）═══
    # 此前这里是硬编码常量，其中两个 MCP 服务在项目里根本不存在。
    # 现在：调用过什么就显示什么，没调用就是空 —— 宁可显示「本轮未检索」，
    # 也不展示没发生的事。
    _calls = {str(c) for c in tool_calls}

    # ═══ 三栏的语义分工（2026-09-22 厘清）═══
    #   skills = 用了什么**编排手艺**（方法论层）
    #   rag    = 查了什么**资料**（数据层）
    #   mcp    = 调了什么**外部服务**
    # 三者不重复 —— 一次工具调用只归其中一栏。

    # Skill：本轮采用的编排手艺。调 SOP 检索 = 用了「派遣编排」这门手艺。
    if "query_orchestration_sop" in _calls:
        trace.skills.append(
            {
                "id": "dispatch_orchestration",
                "name": "派遣编排",
                "detail": "按场景方法论决定派谁、串行还是并行",
            }
        )

    # RAG：本轮检索过的资料（向量库 + 直读配置）
    if "query_orchestration_sop" in _calls:
        trace.rag.append(
            {
                "id": "orchestration_sop",
                "collection": "orchestration_sop",
                "name": "编排 SOP",
                "detail": "送礼 / 对比 / 复盘 / 澄清的编排模板",
            }
        )
    if "list_subagents" in _calls:
        trace.rag.append(
            {
                "id": "subagent_directory",
                "collection": "config",
                "name": "子智能体目录",
                "detail": f"直读配置，可派遣：{', '.join(available_slugs)}",
            }
        )
    if "find_archive" in _calls:
        trace.rag.append(
            {
                "id": "archive_index",
                "collection": "shopping_decisions",
                "name": "购物档案索引",
                "detail": "判断走复盘还是重新选",
            }
        )

    # MCP：本轮真实调用过的 MCP 工具
    # ⚠️ 2026-09-22 删除了 sc.subagent-registry / sc.session-memory 两条 ——
    #    它们**在项目里不存在**，是前端 mock 时代契约文档里的虚构服务。
    _MCP_TOOLS = {
        "taobao_searchMaterial": ("taobao_mcp", "淘宝商品搜索"),
        "taobao_getItemInfo": ("taobao_mcp", "淘宝商品详情"),
        "taobao_convertLink": ("taobao_mcp", "淘宝转链"),
        "pdd_goods_search": ("taobao_mcp", "拼多多商品搜索"),
        "pdd_goods_detail": ("taobao_mcp", "拼多多商品详情"),
        "pdd_goods_recommend": ("taobao_mcp", "拼多多商品推荐"),
        "pdd_goods_prom_url": ("taobao_mcp", "拼多多转链"),
    }
    trace.mcp = [
        {"id": server, "server": server, "name": name, "detail": f"已调用 {tool_name}"}
        for tool_name, (server, name) in _MCP_TOOLS.items()
        if tool_name in _calls
    ]

    selected = list(selected)
    parallel = len(selected) > 1
    trace.dispatch = [
        {
            "slug": display_name(slug),
            "raw_slug": slug,
            "task": task,
            # 无依赖 → 并行；有依赖 → 串行 + depends_on
            "depends_on": [],
            "timeout_ms": 120000,
            "parallel": parallel,
        }
        for slug, task in selected
    ]

    # ── decision 的措辞原则（重要）──
    # 这段文字会展示在卡片上，**模型也看得见**。所以它必须是
    # 「在做什么」的陈述，而不是「为什么不做什么」的答辩。
    # 反面教材（已废弃）：「置信度太低，派出去也只会白跑」「本轮未派遣…」
    #   —— 这类句子一旦进了上下文，模型会学去当对话说出口，
    #      用户打个招呼却读到一段系统日志口吻的自述。
    if not selected:
        trace.decision = "本轮没有需要委托给子智能体的事项。"
    elif parallel:
        names = " + ".join(display_name(s) for s, _ in selected)
        trace.decision = f"同时委托给：{names}"
    else:
        slug, _ = selected[0]
        trace.decision = f"委托给{display_name(slug)}处理"

    return trace


def apply_guardrails(trace: OrchestrationTrace, *, touched_business_data: bool = False) -> OrchestrationTrace:
    """把护栏写进轨迹。生产环境这两个值都应为保守默认。"""
    trace.guardrails = {
        "touched_business_data": touched_business_data,
        "note": ARCHIVE_ONLY_NOTE,
    }
    return trace
