"""独立 agent 共用的「问模型 + 解析」小工具。

═══════════════════════════════════════════════════════════════════════
2026-09-25：为什么把它从两个 stages.py 里抽出来
═══════════════════════════════════════════════════════════════════════

规划（`planning/stages.py`）和送礼（`gift/stages.py`）各自抄了一份
`_get_model` / `ask_model` / `parse_json_block` —— 三对完全一样的函数。

抄两份的代价已经付过一次：`idx` 的校验两处都写成了 `isinstance(v, int)`，
而模型经常回 `"2"` 或 `2.0`，于是**两处同时**静默降级成规则。修一处不改
另一处，就会变成「规划用模型、送礼用规则」这种没法解释的行为差异。

所以：**调用模型的胶水代码只留一份**，改一处即全局生效。
领域逻辑（怎么挑、怎么组合）仍然各写各的，那本来就该不同。
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Callable

logger = logging.getLogger(__name__)

# 单次模型调用上限。超时即降级到规则 —— 推演是后台任务，
# 一次抖动不该让整个 run 失败。
LLM_TIMEOUT = 120

# 独立 agent 用的模型。**与主智能体的 `config.default_model` 分开**。
# ═══════════════════════════════════════════════════════════════════
# 2026-09-25：为什么这里要单独指定
# ═══════════════════════════════════════════════════════════════════
#
# 用户反馈规划执行流「太不实时」。逐层排查后，根因**不是**前端、也不是
# 节流策略，而是模型：默认的 `sensenova-6.8-flash-lite` **不吐推理过程**。
#
# 实测（真实 6 候选提示词，各跑两次）：
#
#   sensenova-6.8-flash-lite   推理 0 块；正文集中在最后 0.2 秒内吐完
#                              （6.68→6.91s、49.04→49.13s）
#   deepseek-v4-flash          推理 82~178 块，持续 1.6~3.7 秒；
#                              正文再 45 块
#
# 也就是说前者是「想 49 秒 → 0.1 秒内全部显示」，后者是「一边想一边显示」。
# 任何前端技巧都补不上这个差别 —— 流里根本没有中间数据。
#
# 用环境变量覆盖，不动全局默认：主智能体那边自有它的取模逻辑，
# 改 `config.default_model` 会连带影响购前/购后助手，超出这次的范围。
INDEPENDENT_MODEL_ENV = "INDEPENDENT_AGENT_MODEL"
INDEPENDENT_MODEL_FALLBACK = "SenseNova/deepseek-v4-flash"

_model = None


def get_model():
    """取独立 agent 用的聊天模型。进程内缓存。

    优先 `INDEPENDENT_AGENT_MODEL` 环境变量，其次内置默认（deepseek-v4-flash，
    因为它吐推理过程），最后才回退到全局 default_model。
    """
    global _model
    if _model is None:
        import os

        from src.agents.common.llm import load_chat_model
        from src.config import config

        spec = (
            os.getenv(INDEPENDENT_MODEL_ENV)
            or INDEPENDENT_MODEL_FALLBACK
            or getattr(config, "default_model", "SenseNova/sensenova-6.8-flash-lite")
        )
        try:
            _model = load_chat_model(spec)
        except Exception as e:
            # 指定的模型不可用时退回全局默认 —— 宁可少一点实时感，
            # 也不能整个推演跑不起来。
            fallback = getattr(config, "default_model", "SenseNova/sensenova-6.8-flash-lite")
            logger.warning(
                "[llm] 独立 agent 模型 %s 不可用（%s），回退到 %s", spec, e, fallback
            )
            _model = load_chat_model(fallback)

        # 限流自动重试。
        # ═══════════════════════════════════════════════════════════════
        # 2026-09-26：为什么必须配这个，而且次数要给够
        # ═══════════════════════════════════════════════════════════════
        # ReAct 循环一轮要发好几个请求（模型→工具→模型→…），很容易撞上
        # TPM 限流。实测跑一次完整的规划会中途吃 429，而**一次 429 就让
        # 整个 run 落 failed** —— 用户看到「任务失败」，其实几秒后就能过。
        #
        # 次数给到 8 而不是 5：这个 provider 的限流是**滚动 TPM 窗口**，
        # 不是固定间隔。撞上时往往要等几十秒窗口滑过去，5 次退避不够用
        # （实测 5 次仍然落 failed）。规划本来就要跑一两分钟，多等一会儿
        # 远好过整个任务失败。
        #
        # SDK 自己按指数退避 + 尊重 Retry-After；只对可重试的错误生效
        # （429/5xx/超时），参数错误照样立刻抛。
        for attr, val in (("max_retries", 8), ("timeout", 120)):
            try:
                if hasattr(_model, attr):
                    setattr(_model, attr, val)
            except Exception:
                pass
    return _model


async def ask_model(
    system: str,
    user: str,
    tag: str = "llm",
    on_delta: Callable[[str], None] | None = None,
) -> str:
    """问一次模型，返回纯文本。**失败返回空串**，由调用方降级到规则。

    失败不抛是有意的：用户宁可看到一份「用了规则兜底」的结果，
    也不想看到「任务失败」。但降级会在事件里**如实标注**，不假装是模型给的。

    `on_delta` 传了就用 `astream` 逐 token 回调，没传就用 `ainvoke` 一次性拿。
    ═══════════════════════════════════════════════════════════════════
    2026-09-25：为什么要逐 token
    ═══════════════════════════════════════════════════════════════════
    原先一律 `ainvoke` —— 模型想 8~12 秒，然后**一次性**吐出全部文字。
    界面上就是「正在思考」静止十几秒，然后突然出现一整段。而主智能体是
    逐字推增量的（chat_stream_service 里取 `reasoning_content` 的差量），
    所以那边「在动」是看得见的。这个差别就是「太不实时」的来源。

    回调是**同步**的（`Callable[[str], None]`）：调用方在事件循环里把它
    转成「发一条 SSE 事件」的异步操作时，自己用 asyncio 队列或 fire-and-forget
    处理。这里不做异步 —— 逐 token 调 `await` 会让每个 token 都排一次队，
    反而拖慢生成。
    """
    try:
        model = get_model()
        messages = [("system", system), ("human", user)]

        if on_delta is None:
            resp = await asyncio.wait_for(
                model.ainvoke(messages), timeout=LLM_TIMEOUT,
            )
            content = getattr(resp, "content", None)
            return (content if isinstance(content, str) else str(content or "")).strip()

        # ── 流式路径 ──
        # 注意：仍要拼出完整文本返回 —— 调用方（parse_json_block）要的是
        # 完整结果，逐字回调只是给界面看的副作用，不改变返回值契约。
        parts: list[str] = []

        async def _consume():
            async for chunk in model.astream(messages):
                content_piece, reason_piece = _chunk_parts(chunk)
                if content_piece:
                    # ⚠️ 只有 content 进 `parts`（返回值要交给 parse_json_block）。
                    # reasoning 是模型的自言自语，混进去会解析出两个 JSON 片段。
                    parts.append(content_piece)
                # 界面优先看**正在想什么**：reasoning 有内容就先播它，
                # 没有才播正文。见 _chunk_parts 的说明。
                piece, kind = ((content_piece, "content") if content_piece
                               else (reason_piece, "reasoning"))
                if not piece:
                    continue
                try:
                    res = on_delta(piece, kind)
                    if asyncio.iscoroutine(res):
                        await res
                except TypeError:
                    # 兼容只收一个参数的回调
                    res = on_delta(piece)
                    if asyncio.iscoroutine(res):
                        await res
                except Exception as e:
                    # 回调失败（比如事件写库出错）不该中断模型生成 ——
                    # 界面少几个字可以接受，整段推理丢掉不行。
                    logger.warning("[%s] on_delta 回调失败（忽略）: %s", tag, e)

        await asyncio.wait_for(_consume(), timeout=LLM_TIMEOUT)
        return "".join(parts).strip()
    except Exception as e:
        logger.warning("[%s] 模型调用失败（降级到规则）: %s: %s", tag, type(e).__name__, e)
        return ""


def _chunk_parts(chunk: Any) -> tuple[str, str]:
    """从一个流式 chunk 里取 `(正文增量, 推理增量)`。

    ═══════════════════════════════════════════════════════════════════
    2026-09-25：为什么要分开取 —— 这是「不实时」的真正原因
    ═══════════════════════════════════════════════════════════════════

    实测（SenseNova）一个 compare 请求：前 ~9 秒 `content` **全是空字符串**，
    模型在内部推理阶段；推理结束后才在 0.1 秒内把正文一次吐完。
    只读 `content` 的话，那 9 秒里我们什么都收不到 —— 界面上就是「正在思考」
    静止不动，然后文字瞬间出现。这正是「太不实时」的根源，不是节流没做好。

    推理内容走 `additional_kwargs.reasoning_content`（DeepSeek 系同款）。
    主智能体也是读这个字段（`chat_stream_service` 里取它的增量），
    所以那边「在动」是看得见的 —— 两边对齐同一套读法。

    返回值分成两路是有意的：
      · 正文进返回值（要交给 parse_json_block）
      · 推理只用于展示，混进正文会让 JSON 解析拿到两段
    """
    content = getattr(chunk, "content", None)
    out: list[str] = []
    if isinstance(content, str):
        out.append(content)
    elif isinstance(content, list):
        # 有些 provider 把 content 包成 [{"type":"text","text":"..."}]
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                out.append(part["text"])
            elif isinstance(part, str):
                out.append(part)

    ak = getattr(chunk, "additional_kwargs", None) or {}
    reason = ak.get("reasoning_content") or ""
    if not isinstance(reason, str):
        reason = ""

    return "".join(out), reason


def _chunk_text(chunk: Any) -> str:
    """只要正文增量（兼容旧调用点）。"""
    return _chunk_parts(chunk)[0]


# 推理流里要**丢掉**的内容。
# ═══════════════════════════════════════════════════════════════════
# 2026-09-25：为什么要在展示层过滤模型的推理
# ═══════════════════════════════════════════════════════════════════
#
# 推理通道（reasoning_content）是模型的**草稿纸**，不是它的回答 ——
# 输出格式的指令管不到它。实测同一个提示词下：
#   · 多数时候推理是纯中文（中文占比 0.96），讲的是候选商品怎么比
#   · 但会间歇性地夹英文（「We need answer in Chinese. Need select best…」）
#     以及复述任务本身（「我们只需要输出JSON」「格式：先两三句判断过程」）
#
# 后者正是用户说的「AI 味」：它在念任务要求，不是在讲这个商品。
# 提示词里喊「不要写英文」治不了 —— 那是草稿纸，本来就不受约束。
# 所以在**展示层**过滤：过滤是「不显示草稿纸上的废话」，不是改写结论，
# 返回值（交给 parse_json_block 的正文）完全不受影响。
#
# 判据刻意保守：只丢「明显是英文」或「明显在念任务」的片段，
# 拿不准的一律保留 —— 宁可多显示一句，也不把真实判断吞掉。
_REASON_NOISE = (
    "we need", "let me", "let's", "i need", "i should", "the user",
    "output format", "json format", "so output", "need answer",
    "输出格式", "输出json", "只输出json", "复述", "格式要求",
)


def filter_reasoning(text: str) -> str:
    """把推理文本里「草稿纸上的废话」按**句子**丢掉，留下真正在讲商品的部分。

    为什么按句子而不是按整段：一段推理里常常是「We need answer. 候选0是汽车
    止震板，装修用不上。Let me pick 3. 3 号标注环保。」——整段丢会连真判断
    一起丢，整段留又全是噪音。按句切分后能只丢那两句废话。

    ⚠️ 切分必须**同时认中英文句末**。只认 `。！？` 的话，英文句子会和后面的
    中文粘成一段，那一段因为含 "we need" 被判成噪音 —— 真判断跟着一起没了
    （实测：整段过滤返回空字符串，四句全丢）。所以英文句号后面**跟空白**时
    也算句末；`42.2` 这种小数点不跟空白，不会被误切。
    """
    if not text:
        return ""
    return "".join(
        p for p in _SENT_SPLIT.split(text) if p and not _is_noisy_reasoning(p)
    )


# 句末边界：中文句末标点/换行，或「英文句号 + 空白」。
# 用 lookbehind/lookahead 不消耗字符，切出来的片段保留标点本身。
_SENT_SPLIT = re.compile(r"(?<=[。！？!?\n])|(?<=\.)(?=\s)")


def _last_sentence_end(buf: str) -> int:
    """buf 里最后一个句末边界的**下标 + 1**；没有边界返回 -1。

    流式攒句时用它决定「发到哪儿为止」——不能把半句话发出去，
    否则过滤判据（按句）会失效。
    """
    last = -1
    for m in _SENT_SPLIT.finditer(buf):
        last = m.end()
    return last


def _is_noisy_reasoning(piece: str) -> bool:
    """这段推理是不是「草稿纸上的废话」（英文 / 念任务要求）。"""
    s = (piece or "").strip()
    if not s:
        return True

    low = s.lower()
    if any(m in low for m in _REASON_NOISE):
        return True

    # 英文字母占「有意义的字符」的比例过高 → 判定为英文草稿。
    # 中文标点、数字不算 —— 纯数字（价格）不该被判成英文。
    letters = [c for c in s if c.isascii() and c.isalpha()]
    cjk = [c for c in s if "一" <= c <= "鿿"]
    if not cjk and len(letters) >= 6:
        return True
    if letters and len(letters) / max(1, len(letters) + len(cjk)) > 0.6:
        return True
    return False


# 让模型「先说人话，再给机器读的 JSON」。加在 system 末尾，不改各 stage 的措辞。
STREAMING_CONTRACT = (
    "\n\n---\n"
    "输出格式（重要）：**先用两三句话写出你的判断过程**，再另起一行给出 JSON。"
    "判断过程是给人看的，要写清你在比较什么、为什么排除某个候选。"
    "不要复述这些要求，也不要写「让我分析一下」「首先…其次…」这类过场话。"
)


async def ask_model_streaming(
    system: str,
    user: str,
    on_text: Callable[[str, str], Any],
    tag: str = "llm",
) -> str:
    """流式问一次模型：把**推理过程**逐段回调出去。

    ═══════════════════════════════════════════════════════════════════
    两路文本，分别对待
    ═══════════════════════════════════════════════════════════════════

    实测这个模型（SenseNova）的流有**两个阶段**：

      ① 推理阶段：`content` 恒为空，推理写在 `additional_kwargs.reasoning_content`
         —— 占整个请求的大部分时间（compare 约 9 秒）
      ② 输出阶段：推理结束后，正文在 0.1 秒内一次性吐完

    所以「实时」的关键是**播阶段 ①**。只播正文的话，界面在整个思考期间
    都是静止的，然后文字瞬间冒出来 —— 那正是「太不实时」的观感来源。

    回调签名 `(text, kind)`，kind ∈ {"reasoning", "content"}：前端据此
    决定这段是「它在想」还是「它的结论」。推理里出现的 `{` 不做切分 ——
    推理是自由文本，不是 JSON；只有 content 阶段才需要掐掉 JSON 部分。

    返回值仍是完整正文，交给 `parse_json_block` 照旧解析。
    """
    parts: list[str] = []
    seen_json = False
    # 推理按**句子**攒着：过滤要以整句为判据（见 filter_reasoning），
    # 而 chunk 是逐字来的，不攒就会把「We need」和「answer in Chinese」拆开判，
    # 两句都不像噪音，于是都漏过去。
    reason_buf: list[str] = []

    async def _emit(text: str, kind: str) -> None:
        if not text:
            return
        res = on_text(text, kind)
        if asyncio.iscoroutine(res):
            await res

    async def _flush_reason(force: bool = False) -> None:
        """把攒够整句的推理过滤后发出去。force=True 时连残句一起发。"""
        buf = "".join(reason_buf)
        reason_buf.clear()
        if not buf:
            return
        if not force:
            # 只发到最后一个句末边界为止，剩下的留到下次 ——
            # 半句话发出去会让「按句过滤」失效（判据要看整句）。
            cut = _last_sentence_end(buf)
            if cut <= 0:
                reason_buf.append(buf)   # 还没凑够一句，继续攒
                return
            head, tail = buf[:cut], buf[cut:]
            if tail:
                reason_buf.append(tail)
            buf = head
        await _emit(filter_reasoning(buf), "reasoning")

    async def _on_delta(piece: str, kind: str) -> None:
        nonlocal seen_json
        if kind == "reasoning":
            reason_buf.append(piece)
            await _flush_reason()
            return
        # 正文开始 → 推理结束了，把残句发掉再切到正文
        await _flush_reason(force=True)
        if seen_json:
            return
        # 正文阶段：同一段里可能既含散文又含 JSON 的开头，只播 `{` 之前的部分
        cut = piece.find("{")
        if cut >= 0:
            await _emit(piece[:cut], "content")
            seen_json = True
        else:
            await _emit(piece, "content")

    text = await ask_model(system + STREAMING_CONTRACT, user, tag=tag, on_delta=_on_delta)
    return text


class DeltaPump:
    """把同步的逐字回调，转成**节流**的异步事件。

    ═══════════════════════════════════════════════════════════════════
    为什么不能每来一个字就写一条事件
    ═══════════════════════════════════════════════════════════════════

    模型每秒能吐几十个 token，而每次 emit 都是一次 DB 写 + 一次 commit
    （planning/gift 的事件都落库）。逐字写会把一个 run 的事件表撑到几千行，
    还会因为反复 commit 拖慢模型生成 —— 界面反而更卡。

    所以：同步回调只往缓冲里塞，后台任务每 `interval` 秒（或攒够
    `max_chars`）把缓冲**合并成一条**发出去。前端拿到的是「一段一段长出来」，
    观感与逐字几乎无异，事件量却从几千条降到十几条。

    用法：
        pump = DeltaPump(emit_fn)      # emit_fn: async (text) -> None
        await ask_model(..., on_delta=pump.feed)
        await pump.close()             # 别忘了，否则最后一段会丢
    """

    def __init__(
        self,
        flush: Callable[..., Any],
        interval: float = 0.22,
        max_chars: int = 90,
        filter_reasoning_text: bool = False,
    ) -> None:
        self._flush = flush
        self._interval = interval
        self._max_chars = max_chars
        # 推理是否过噪音过滤（见 filter_reasoning）。
        # 过滤要**按整句**判，所以开了这个开关时 reasoning 会攒到句末才发。
        self._filter_reason = filter_reasoning_text
        # 按 kind 分桶：reasoning 与 content 是两种不同的东西，混在一个
        # 缓冲里会拼出「推理正文」这种四不像的段落，前端也没法区别渲染。
        self._buf: dict[str, list[str]] = {}
        self._task: asyncio.Task | None = None
        self._closed = False

    def feed(self, piece: str, kind: str = "content") -> None:
        """同步回调入口 —— 由模型流调用，绝不能阻塞。"""
        if self._closed or not piece:
            return
        bucket = self._buf.setdefault(kind, [])
        bucket.append(piece)

        # 推理过滤要按**整句**判（见 filter_reasoning），所以句末没到就先攒着，
        # 不然「We need」和「answer in Chinese」会被拆成两段、都判不出是噪音。
        if self._filter_reason and kind == "reasoning":
            if _last_sentence_end("".join(bucket)) <= 0:
                return   # 还没凑够一句，等下一批

        if sum(len(x) for x in bucket) >= self._max_chars:
            # 攒够了就立刻起一个 flush，不等下一个 tick
            self._schedule()
        elif self._task is None or self._task.done():
            self._schedule()

    def _schedule(self) -> None:
        if self._task is not None and not self._task.done():
            return
        try:
            self._task = asyncio.create_task(self._run())
        except RuntimeError:
            # 没有运行中的事件循环（比如同步测试里）—— 退回立即直发
            self._drain_now()

    async def _run(self) -> None:
        # 循环条件用「有没有待发的」而不是「有没有正在跑的」——
        # 原先写成 `while ... and self._buf`，一旦缓冲被排空就退出，
        # 之后 feed 又起新任务；任务切换有延迟，实测会把整段推理攒到最后
        # 一次性发出（正是我们要消灭的「不实时」）。
        while not self._closed and any(self._buf.values()):
            await asyncio.sleep(self._interval)
            await self._drain()

    async def _drain(self) -> None:
        for kind in list(self._buf.keys()):
            bucket = self._buf.get(kind) or []
            if not bucket:
                continue
            text = "".join(bucket)
            bucket.clear()
            if not text:
                continue
            if self._filter_reason and kind == "reasoning":
                # 只发到最后一个句末，剩下的留到下次（半句判不出噪音）
                cut = _last_sentence_end(text)
                if cut <= 0:
                    bucket.append(text)
                    continue
                tail, text = text[cut:], text[:cut]
                if tail:
                    bucket.append(tail)
                text = filter_reasoning(text)
                if not text:
                    continue
            await self._flush_text(text, kind)

    async def _flush_text(self, text: str, kind: str) -> None:
        try:
            res = self._flush(text, kind)
            if asyncio.iscoroutine(res):
                await res
        except TypeError:
            # 兼容只收一个参数的回调
            res = self._flush(text)
            if asyncio.iscoroutine(res):
                await res
        except Exception as e:
            # 发事件失败不该中断模型生成 —— 少显示几个字可以接受
            logger.warning("[DeltaPump] flush 失败（忽略）: %s", e)

    def _drain_now(self) -> None:
        for kind, bucket in list(self._buf.items()):
            text = "".join(bucket)
            bucket.clear()
            if text:
                try:
                    self._flush(text, kind)
                except Exception:
                    pass

    async def close(self) -> None:
        """收尾：停掉后台任务，把剩下的一起发出去。

        ⚠️ 不能只调 `_drain()`：开了推理过滤时 `_drain` 会把「还没到句末」
        的尾巴留在缓冲里（那是设计如此，避免半句判不出噪音）。收尾时必须
        把残句也发掉，否则最后一段推理永远不显示。
        """
        self._closed = True
        task, self._task = self._task, None
        if task is not None and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        await self._drain()
        # 残句：过滤后仍要发（按整段判一次，能过滤就过滤，不能就原样发）
        for kind, bucket in list(self._buf.items()):
            text = "".join(bucket)
            bucket.clear()
            if not text:
                continue
            if self._filter_reason and kind == "reasoning":
                text = filter_reasoning(text)
                if not text:
                    continue
            await self._flush_text(text, kind)


def parse_json_block(text: str) -> dict | None:
    """从模型回复里抠 JSON 对象。容忍 ```json 包裹与前后说明文字。

    严格解析失败时**再试一次修复**，见 `_repair_json`。
    """
    if not text:
        return None
    t = text.strip()
    if t.startswith("```"):
        parts = t.split("```")
        t = parts[1] if len(parts) > 1 else t
        if t.lstrip().lower().startswith("json"):
            t = t.lstrip()[4:]
    i, j = t.find("{"), t.rfind("}")
    if i < 0 or j <= i:
        return None
    blob = t[i:j + 1]

    for candidate in (blob, _repair_json(blob)):
        try:
            obj = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(obj, dict):
            return obj
    return None


# 字符串里必须转义的控制字符 → 转义序列
_CTRL_ESCAPE = {"\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _repair_json(t: str) -> str:
    """修 LLM 最常见的两种非法 JSON，修不动就原样返回（交给调用方降级）。

    ═══════════════════════════════════════════════════════════════════
    为什么需要它 —— 2026-09-25 实测栽的坑
    ═══════════════════════════════════════════════════════════════════

    模型写了一串**完全正确**的推理，`idx` 也选对了，却因为理由里出现了
    未转义的英文双引号而整块作废：

        {"idx": 3, "why": "候选2虽标"静音王"但用途描述笼统，……"}

    `json.loads` 在这里报 `Expecting ',' delimiter`，于是 `parse_json_block`
    返回 None → 上层以为「模型没按契约答」→ 静默降级成 `min(price)`。
    界面上看到的是一句「模型不可用，已降级为规则」，而模型其实答得好好的。

    中文模型尤其容易这样：它想引用一个词，中文里该用「」或“”，
    但它顺手打了 ASCII 的 `"`。**这是模型的书写习惯，不是它答错了** ——
    所以该修的是解析器，不是提示词里再喊一遍（喊了也还会犯）。

    修复的两类问题：
      1. 字符串**内部**未转义的 `"`  → 补成 `\\"`
      2. 字符串**内部**的裸换行/制表 → 补成 `\\n` / `\\t`

    判定「引号是结束还是内部」的办法：看它后面第一个非空白字符。
      · key 的结束引号后面必然是 `:`
      · value 的结束引号后面必然是 `,` `}` `]` 或到头了
    其余一律当成正文里的引号 —— 因为正文里引用一个词时，后面跟的是
    汉字，不会正好是这些分隔符。
    """
    out: list[str] = []
    i, n = 0, len(t)
    in_str = False
    expecting_key = False

    while i < n:
        c = t[i]

        if not in_str:
            out.append(c)
            if c == '"':
                in_str = True
            elif c in "{[":
                expecting_key = c == "{"
            elif c == ",":
                expecting_key = True
            elif c == ":":
                expecting_key = False
            i += 1
            continue

        # ── 字符串内部 ──
        if c == "\\":
            # 已有的转义序列整体搬过去，别重复转义
            out.append(c)
            if i + 1 < n:
                out.append(t[i + 1])
            i += 2
            continue

        if c == '"':
            j = i + 1
            while j < n and t[j] in " \t\r\n":
                j += 1
            nxt = t[j] if j < n else ""
            closes = (nxt == ":") if expecting_key else (nxt in ",}]" or nxt == "")
            if closes:
                in_str = False
                out.append(c)
            else:
                out.append('\\"')   # 正文里的引号
            i += 1
            continue

        if c in _CTRL_ESCAPE:
            out.append(_CTRL_ESCAPE[c])
            i += 1
            continue

        out.append(c)
        i += 1

    return "".join(out)



def as_idx(v: Any) -> int | None:
    """把模型给的编号收敛成 int，失败返回 None。

    模型经常把数字包成字符串（`"idx": "2"`）或带小数（`2.0`）——
    只认 `isinstance(v, int)` 会把这两种都判成失败，然后静默降级成规则，
    线上看起来就像「模型没用上」。这里一次性认全。

    注意 `bool` 要排除：`True` 是 `int` 的子类，会把 `{"idx": true}`
    当成编号 1。
    """
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, int):
        return v
    try:
        f = float(str(v).strip())
    except (TypeError, ValueError):
        return None
    return int(f) if f.is_integer() else None


def degrade_note(reply: str, parsed: Any, tag: str) -> None:
    """降级时留痕。

    降级本身没问题，但降级必须是**看得见**的：不打日志的话，线上只会看到
    一句「已降级为规则」，却不知道模型到底回了什么 —— 上一轮 compare
    阶段静默就是栽在「失败不留痕」上。
    """
    logger.warning(
        "[%s] 模型输出未按契约，已降级为规则：回复=%r 解析结果=%r",
        tag, (reply or "")[:400], parsed,
    )
