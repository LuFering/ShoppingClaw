"""送礼推演的状态图。

形态：**单图 + 七步**。

    understand → extract → search → verify → combine → message → END

═══════════════════════════════════════════════════════════════════════
2026-09-25 修正：这张图此前**从未被执行过**
═══════════════════════════════════════════════════════════════════════

初版把图写在这儿，然后在 `gift_service.advance()` 里另写了一个 for 循环
真跑 —— 两份实现，读者会以为跑的是图。现在图是**唯一**的推进路径：
service 只负责订阅图的事件、落库、处理中断，不再自己串流程。

分工：
  · 图          —— 流程定义 + 每一步的判断（节点里真调模型/工具）
  · gift_service —— 订阅 stream、写事件、维护快照、等用户拍板

事件由节点通过 `emit` 回调发出（defer=True 的 run 才需要）；
service 把回调塞进 config，图不认识 DB。
"""
from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph import END, START, StateGraph



def _keep(old, new):
    """列表/字典用「后写覆盖」，允许显式置空。"""
    return new if new is not None else old


class GiftState(TypedDict, total=False):
    # 入口参数
    recipient: str
    occasion: str
    budget: int
    signals: list[str]
    run_id: str
    user_id: str

    # 累积产物
    context: dict          # 读到的档案
    profile: list[dict]    # 中栏五组
    understanding: dict
    picked: list[dict]
    excluded: list[dict]
    plan: dict
    budget_rows: list[dict]
    order: dict
    message: dict
    supply: list[dict]
    compare: list[dict]
    question: dict | None


def build_gift_graph():
    """编译送礼图。

    ⚠️ 图**不产生事件** —— 节点只算状态，事件由 service 的 `_on_debug` /
    `_on_node` 按「哪个节点产出了什么」翻译并落库。

    2026-09-27：原先这里有一套 `_emit(config, ...)` 回调机制，但
    `gift_service` 调 `astream(state)` 时**没传 config**，于是
    `config.configurable.emit` 恒为 None —— 那 11 处调用**从未执行过**
    （实测事件表里从来没有 `profile_batch`）。现已全部删除：留着会让
    下一个读代码的人以为图在发事件。真要接上还会与 service 重复发同一批
    事件（变成双份），所以正确的出口只有一个 —— service。
    """
    from src.agents.independent.gift import stages as st

    # ═══════════════════════════════════════════════════════════════════
    # 「理解关系」拆成**两个节点** —— 为了让档案分批到达是真的
    # ═══════════════════════════════════════════════════════════════════
    # 2026-09-27：原来是一个 understand 节点里串行调两次工具、组装五组、
    # 一次性返回，于是中栏在第 25ms 亮出全部五组、之后再无变化 —— 看起来
    # 是张静态卡片。用户要的是「随推演逐步长成完整档案」。
    #
    # 为什么拆节点而不是在代码里 sleep：事件只能在**节点边界**发出
    # （`_on_debug` 在节点开始、`_on_node` 在节点结束）。在服务里 sleep
    # 制造节奏是**演的**；拆成两个节点后，两次 RAG 往返本来就是两次独立
    # 往返，到达时刻是真的 —— 实测 understand 总耗时 5.4s。这是拿真实
    # 的时间差做生长感，不是把一次性数据拉长。
    #
    # 两个节点映射到**同一个左栏步骤**（都叫 understand）：对用户而言那
    # 仍是「理解关系」这一步，只是它内部有两个小阶段。
    async def n_read_history(state: GiftState, config=None) -> dict:
        """读历史决策记录 → 产出 关系 / 生活状态 / 禁忌 / 送礼偏好 四组。

        ⚠️ 返回的 profile 是**部分的四组**，不是完整五组：service 在节点
        边界推事件时只推本节点真正产出的那几组（见 gift_service._PROFILE_BATCH）。
        下一节点会用完整五组覆盖它，所以最终落库的仍是对的。
        """
        history = await st.read_history(state)
        ctx = {"history": history, "prefs": [], "raw_ok": bool(history)}
        # giftpref（送礼偏好）只依赖 state.signals（入口页勾选），不需工具 ——
        # 与这三组同批产出。别漏了它：漏掉的话它永远不会到达中栏。
        return {"context": ctx,
                "profile": st.build_profile(
                    state, ctx,
                    only=("relation", "life", "taboo", "giftpref"))}

    async def n_read_prefs(state: GiftState, config=None) -> dict:
        """读长期偏好 → 支撑 已知喜好；并组装**完整五组**落 state。

        完整五组必须在这里就位：落库与下游（`combine` 要读禁忌）都得拿到
        全的。分批只是**推送**的粒度，不是数据的粒度。
        """
        prev = state.get("context") or {}
        prefs = await st.read_preferences(state)
        ctx = {"history": prev.get("history") or [], "prefs": prefs,
               "raw_ok": bool(prev.get("raw_ok") or prefs)}
        return {"context": ctx, "profile": st.build_profile(state, ctx)}

    async def n_extract(state: GiftState, config=None) -> dict:
        u = await st.build_understanding(state, state.get("profile") or [], state.get("context") or {})
        return {"understanding": u}

    async def n_search(state: GiftState, config=None) -> dict:
        picked = await st.search_candidates(state)
        return {"picked": picked}

    async def n_verify(state: GiftState, config=None) -> dict:
        p, e = st.verify_candidates(state.get("picked") or [], state)
        return {"picked": p, "excluded": e}

    async def n_combine(state: GiftState, config=None) -> dict:
        plan, rows, order = await st.combine(
            state.get("picked") or [],
            {**state, "_profile": state.get("profile") or []},
            state.get("understanding") or {},
        )
        return {"plan": plan, "budget_rows": rows, "order": order}

    async def n_message(state: GiftState, config=None) -> dict:
        msg = await st.build_message(state, state.get("plan") or {},
                                     state.get("understanding") or {})
        supply = st.build_supply(state.get("picked") or [], state.get("plan") or {})
        return {"message": msg, "supply": supply}

    g = StateGraph(GiftState)
    for name, fn in (
        ("read_history", n_read_history), ("read_prefs", n_read_prefs),
        ("extract", n_extract),
        ("search", n_search), ("verify", n_verify),
        ("combine", n_combine), ("message", n_message),
    ):
        g.add_node(name, fn)

    g.add_edge(START, "read_history")
    for a, b in (
        ("read_history", "read_prefs"), ("read_prefs", "extract"),
        ("extract", "search"), ("search", "verify"),
        ("verify", "combine"), ("combine", "message"),
    ):
        g.add_edge(a, b)
    g.add_edge("message", END)
    return g.compile()


_compiled = None


def get_gift_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_gift_graph()
    return _compiled
