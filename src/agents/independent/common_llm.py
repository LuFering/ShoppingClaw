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
from typing import Any

logger = logging.getLogger(__name__)

# 单次模型调用上限。超时即降级到规则 —— 推演是后台任务，
# 一次抖动不该让整个 run 失败。
LLM_TIMEOUT = 120

_model = None


def get_model():
    """取默认聊天模型（与主智能体同源，走项目既有配置）。进程内缓存。"""
    global _model
    if _model is None:
        from src.agents.common.llm import load_chat_model
        from src.config import config

        _model = load_chat_model(
            getattr(config, "default_model", "SenseNova/sensenova-6.8-flash-lite")
        )
    return _model


async def ask_model(system: str, user: str, tag: str = "llm") -> str:
    """问一次模型，返回纯文本。**失败返回空串**，由调用方降级到规则。

    失败不抛是有意的：用户宁可看到一份「用了规则兜底」的结果，
    也不想看到「任务失败」。但降级会在事件里**如实标注**，不假装是模型给的。
    """
    try:
        resp = await asyncio.wait_for(
            get_model().ainvoke([("system", system), ("human", user)]),
            timeout=LLM_TIMEOUT,
        )
        content = getattr(resp, "content", None)
        return (content if isinstance(content, str) else str(content or "")).strip()
    except Exception as e:
        logger.warning("[%s] 模型调用失败（降级到规则）: %s: %s", tag, type(e).__name__, e)
        return ""


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
