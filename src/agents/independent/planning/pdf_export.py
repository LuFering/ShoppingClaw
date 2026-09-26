"""把采购规划交付物导出为 PDF —— 用容器里已有的 PyMuPDF，不新增依赖。

═══════════════════════════════════════════════════════════════════════
2026-09-27：为什么是 PDF，为什么用 PyMuPDF
═══════════════════════════════════════════════════════════════════════

用户原话：「交付类型也可以丰富一些，不要局限于表格和 markdown 文件，
pdf、饼图等等都可以纳入」。

选 PyMuPDF 而不是 reportlab / weasyprint，有两个具体理由：

1. **它已经在 `pyproject.toml` 里**（`pymupdf>=1.25.5`，RAG 那边在用）。
   新增依赖意味着改 Dockerfile、重建镜像；而这份 PDF 只是把已经算好的
   结构化数据排版出来，不值得为此引入一个新的重型依赖。

2. **它自带中日韩字体**（`china-s` / `china-ss` 这些内置 CID 字体）。
   别的方案要么打包一个几 MB 的字体文件、要么依赖系统装了中文字体 ——
   而这台服务器上**一个中文字体都没有**（实测 `fc-list :lang=zh` 为空），
   走系统字体那条路在部署环境里会直接渲染成方块。

⚠️ 中文字体必须显式指定 fontname，否则默认字体画不出汉字。
实测 `china-s`（宋体）可用。

这个模块**只做排版**，不重新计算任何业务数字 —— 数据全部来自
`stages.build_report_doc` 已经算好的结构。数字算两遍必然漂。
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════
# 字体：**中西文分开用两套**
# ═══════════════════════════════════════════════════════════════════
# 内置的 `china-s` / `china-ss` 是**全角等宽**字体 —— 它连阿拉伯数字
# 都按全角渲染。实测把「¥10418.9」画出来是「¥ 1 0 4 1 8 . 9」，数字之间
# 空得离谱，一份满是金额的报告读起来很难受。
#
# 而且它的字宽与字号**不成 0.52 的关系**（实测 CJK 字符 ≈ 1.34×字号，
# 数字 = 1.0×字号），按常规比例估算折行会把右边裁掉。
#
# 所以：汉字走 china-s（必须显式指定，否则画不出来），
# 数字与拉丁字母走 helv（比例字体，正常观感）。
CJK_FONT = "china-s"
CJK_FONT_BOLD = "china-ss"
LAT_FONT = "helv"
LAT_FONT_BOLD = "hebo"

# 页面度量（pt）
PAGE_W, PAGE_H = 595, 842          # A4
MARGIN = 56
LINE = 16.5                        # 正文行高
CONTENT_W = PAGE_W - 2 * MARGIN

# 版面配色（与前端同一套语义，但 PDF 是静态的，用浅一档）
C_TEXT = (0.16, 0.18, 0.20)
C_MUTED = (0.42, 0.45, 0.48)
C_FAINT = (0.60, 0.62, 0.64)
C_ACCENT = (0.72, 0.45, 0.10)
C_RULE = (0.85, 0.86, 0.84)

# 饼图配色。与前端 planningGraphStyle 的色板同源，保证两种交付物观感一致。
PIE_COLORS = [
    (0.58, 0.51, 0.80), (0.43, 0.78, 0.65), (0.55, 0.72, 0.96),
    (0.96, 0.74, 0.09), (0.95, 0.49, 0.49), (0.57, 0.55, 0.55),
    (0.85, 0.65, 0.23), (0.36, 0.62, 0.80),
]


class _Page:
    """一页画布 + 光标。翻页逻辑收在这里，正文代码不必自己管 y 坐标。"""

    def __init__(self, doc):
        self.doc = doc
        self.page = doc.new_page(width=PAGE_W, height=PAGE_H)
        self.y = MARGIN

    def need(self, h: float) -> None:
        """剩余空间不够就翻页。"""
        if self.y + h > PAGE_H - MARGIN:
            self.page = self.doc.new_page(width=PAGE_W, height=PAGE_H)
            self.y = MARGIN

    def text(self, s: str, size: float = 10, color=C_TEXT, bold: bool = False,
             indent: float = 0, line: float = LINE, width: float | None = None,
             x: float | None = None) -> None:
        """写一段会自动折行的文字。**中西文分别用各自的字体**落字。

        同一行里汉字与数字交替出现（「床垫 ¥2649（25%）」），所以按
        「连续同语种」切成若干 run，逐个 run 用对应字体画、按实测宽度推进 x。
        整行统一用一个字体的话，要么汉字画不出（helv 没有汉字），
        要么数字变全角（china-s 是等宽全角）。
        """
        if not s:
            return
        start_x = MARGIN + indent if x is None else x
        avail = (width if width is not None else CONTENT_W) - indent
        for chunk in _wrap(str(s), avail, size, bold):
            self.need(line)
            cx = start_x
            for run, cjk in _runs(chunk):
                f = ((CJK_FONT_BOLD if cjk else LAT_FONT_BOLD) if bold
                     else (CJK_FONT if cjk else LAT_FONT))
                self.page.insert_text((cx, self.y), run,
                                      fontname=f, fontsize=size, color=color)
                cx += sum(_char_w(c, size, bold) for c in run)
            self.y += line

    def line(self, s: str, x: float, y: float, size: float = 10,
             color=C_TEXT, bold: bool = False) -> None:
        """在**指定的 (x, y)** 画一行、不折行。饼图图例要自己控 y 轴，用这个。"""
        cx = x
        for run, cjk in _runs(str(s)):
            f = ((CJK_FONT_BOLD if cjk else LAT_FONT_BOLD) if bold
                 else (CJK_FONT if cjk else LAT_FONT))
            self.page.insert_text((cx, y), run, fontname=f, fontsize=size, color=color)
            cx += sum(_char_w(c, size, bold) for c in run)

    def gap(self, h: float = 6) -> None:
        self.y += h

    def rule(self) -> None:
        self.need(8)
        self.page.draw_line((MARGIN, self.y), (PAGE_W - MARGIN, self.y),
                            color=C_RULE, width=0.7)
        self.y += 8


def _runs(s: str) -> list[tuple[str, bool]]:
    """把字符串切成「连续同语种」的段：[(文本, 是否CJK), …]。

    用于中西文混排 —— 见 _Page.text 的说明。
    """
    out: list[tuple[str, bool]] = []
    cur, flag = "", None
    for ch in s:
        c = _is_cjk(ch)
        if flag is None or c == flag:
            cur += ch
        else:
            out.append((cur, flag))
            cur, flag = ch, c
        flag = c
    if cur:
        out.append((cur, bool(flag)))
    return out


def _is_cjk(ch: str) -> bool:
    """这个字符该用中文字体画吗。

    阈值取 0x2E80（CJK 部首扩展起点）—— 覆盖汉字、假名、全角标点
    （，。「」等都在 0x3000 段）。ASCII 与拉丁扩展字母走比例字体。
    """
    return ord(ch) > 0x2E80


# 字宽缓存：同一份报告里同一个字要量很多次，PyMuPDF 的测量是纯函数
_W = {}


def _char_w(ch: str, size: float, bold: bool = False) -> float:
    """单个字符的**实测**宽度。

    ⚠️ 必须实测，不能按比例估。前面踩过：按「ASCII = 0.52×字号」估，
    而 china-s 里数字实际是 1.0×字号，于是每行都超出边界被裁掉。
    """
    key = (ch, size, bold)
    hit = _W.get(key)
    if hit is not None:
        return hit
    import fitz
    if _is_cjk(ch):
        f = CJK_FONT_BOLD if bold else CJK_FONT
    else:
        f = LAT_FONT_BOLD if bold else LAT_FONT
    try:
        w = fitz.get_text_length(ch, fontname=f, fontsize=size)
    except Exception:
        # 量不出来就退回一个保守估值（宁可折早一点，也别画出界）
        w = size * (1.0 if _is_cjk(ch) else 0.55)
    _W[key] = w
    return w


def _wrap(s: str, avail: float, size: float, bold: bool = False) -> list[str]:
    """按可用宽度折行。返回若干行文本。

    不用 PyMuPDF 的 textbox 是因为它要预先给出矩形高度，而我们的内容
    高度得先知道才能决定翻不翻页 —— 自己折行反而更直接。
    """
    if not s:
        return []
    out, cur, w = [], "", 0.0
    for ch in s:
        if ch == "\n":
            out.append(cur)
            cur, w = "", 0.0
            continue
        # 行首不留空格（折行后常见）
        if ch == " " and not cur:
            continue
        cw = _char_w(ch, size, bold)
        if w + cw > avail and cur:
            out.append(cur)
            cur, w = "", 0.0
            if ch == " ":
                continue
        cur += ch
        w += cw
    if cur:
        out.append(cur)
    return out


def _money(v: Any) -> str:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return "—"
    return f"¥{f:,.0f}" if abs(f) >= 1 else f"¥{f:g}"


def _pie(page: _Page, chart: dict) -> None:
    """在当前位置画一个预算构成饼图 + 图例。

    ⚠️ 画的是**真实占比**；「未动用」不画进饼里 —— 否则「没花的钱」
    看起来像花掉了。它单独写在图例下方。
    """
    series = [x for x in (chart.get("series") or []) if x.get("value")]
    if not series:
        return
    total = sum(x["value"] for x in series)
    if total <= 0:
        return

    r = 62
    cx, cy = MARGIN + r + 8, page.y + r + 6
    page.need(2 * r + 40)

    import math
    # ⚠️ `draw_sector(center, arc_end_point, beta_degrees)` —— 三个参数是
    # **圆心 / 弧的起点 / 张角**，不是矩形框。
    # 我第一版按「矩形 + 起止角」写了，报 `Point: bad seq len`；
    # 第二版又想用 draw_polygon 手搓，但 Page 上没这个方法（只有 Shape 有）。
    # 这里按真实签名来：每段都从同一根射线（12 点方向）起算会叠在一起，
    # 所以要先把「累计角度」算出来，再传每段的**起始点**与**张角**。
    start = -90.0
    for i, seg in enumerate(series):
        sweep = seg["value"] / total * 360.0
        rad = math.radians(start)
        arc_start = (cx + r * math.cos(rad), cy + r * math.sin(rad))
        color = PIE_COLORS[i % len(PIE_COLORS)]
        page.page.draw_sector((cx, cy), arc_start, sweep,
                              color=color, fill=color, width=0)
        start += sweep

    # 图例：色块 + 品类 + 金额 + 占比
    # 走 page.line() 而不是裸 insert_text —— 它负责中西文分字体（见其说明），
    # 金额里的数字才不会渲染成全角。
    lx = MARGIN + 2 * r + 26
    ly = cy - r + 4
    for i, seg in enumerate(series):
        color = PIE_COLORS[i % len(PIE_COLORS)]
        page.page.draw_rect((lx, ly - 7, lx + 8, ly + 1), color=color, fill=color, width=0)
        pct = seg["value"] / total * 100
        page.line(f"{seg['name']}　{_money(seg['value'])}（{pct:.0f}%）",
                  x=lx + 14, y=ly, size=9.5, color=C_TEXT)
        ly += 15

    page.y = cy + r + 16
    if chart.get("remaining"):
        page.text(f"预算另有余量 {_money(chart['remaining'])} 未动用（未计入上图）。",
                  size=9, color=C_MUTED)
    if chart.get("missing"):
        page.text(f"⚠️ {'、'.join(chart['missing'])} 未估出用量，未计入上图。",
                  size=9, color=C_ACCENT)


def build_report_pdf(doc_data: dict) -> bytes:
    """把报告结构渲染成 PDF，返回字节。

    只接受 `kind == 'report'` 的结构；其它类型返回空 bytes，
    由调用方决定降级（不在这里猜怎么画）。
    """
    import fitz

    if not doc_data or doc_data.get("kind") != "report":
        return b""

    d = fitz.open()
    p = _Page(d)

    # ── 页头 ──
    p.text(doc_data.get("title") or "采购规划报告", size=17, bold=True)
    p.gap(2)
    meta = " · ".join(x for x in [
        f"预算 {doc_data.get('budget')}" if doc_data.get("budget") else "",
        f"周期 {doc_data.get('duration')}" if doc_data.get("duration") else "",
        f"硬约束 {'、'.join(doc_data['constraints'])}" if doc_data.get("constraints") else "",
    ] if x)
    if meta:
        p.text(meta, size=9.5, color=C_MUTED)
    p.rule()

    # ── 摘要：整份报告最先被读到的几行 ──
    if doc_data.get("summary"):
        p.text(doc_data["summary"], size=11, color=C_TEXT)
        p.gap(4)

    # ── 关键数字一行 ──
    h = doc_data.get("headline") or {}
    facts = [f"{h.get('categories', 0)} 个品类"]
    if h.get("total") is not None:
        facts.append(f"估算 {_money(h['total'])}")
    if h.get("ratio") is not None:
        facts.append(f"占预算 {h['ratio'] * 100:.0f}%")
    if h.get("remaining") is not None:
        facts.append(f"结余 {_money(h['remaining'])}")
    facts.append(f"浏览候选 {h.get('candidates', 0)} 件（排除 {h.get('excluded', 0)}）")
    p.text("　·　".join(facts), size=9.5, color=C_MUTED)
    p.gap(6)

    # ── 饼图 ──
    _pie(p, doc_data.get("chart") or {})

    # ── 整体取舍 ──
    if doc_data.get("thesis"):
        p.rule()
        p.text("整体取舍", size=12, bold=True)
        p.text(doc_data["thesis"], size=10, color=C_TEXT)
        p.gap(4)

    # ── 逐品类：报告的主体，要能照着它下单 ──
    for i, sec in enumerate(doc_data.get("sections") or [], 1):
        p.rule()
        cat = sec.get("category") or f"第 {i} 项"
        p.text(f"{i}. {cat}", size=12, bold=True)
        p.text(sec.get("name") or "—", size=10.5, color=C_TEXT)
        if sec.get("price") is not None:
            line = f"单价 {_money(sec['price'])}"
            if sec.get("quantity"):
                line += f" × {sec['quantity']:g}"
                if sec.get("subtotal") is not None:
                    line += f" = {_money(sec['subtotal'])}"
            p.text(line, size=9.5, color=C_ACCENT)
        if sec.get("quantity_basis"):
            p.text(f"用量依据：{sec['quantity_basis']}", size=9, color=C_FAINT)
        if sec.get("why"):
            p.gap(2)
            p.text(sec["why"], size=10, color=C_TEXT)
        if sec.get("alternatives"):
            p.gap(2)
            p.text("同品类其他候选", size=9, color=C_FAINT)
            for a in sec["alternatives"]:
                pr = f"　{_money(a['price'])}" if a.get("price") is not None else ""
                p.text(f"· {a['name']}{pr}", size=9.5, color=C_MUTED, indent=10)
        if sec.get("excluded"):
            p.text("已排除", size=9, color=C_FAINT)
            for e in sec["excluded"]:
                pr = f"　{_money(e['price'])}" if e.get("price") is not None else ""
                p.text(f"· {e['name']}{pr} —— {e.get('reason') or '不满足硬约束'}",
                       size=9.5, color=C_MUTED, indent=10)
        p.gap(6)

    # ── 风险与页脚 ──
    if doc_data.get("risks"):
        p.rule()
        p.text("风险与待确认", size=12, bold=True)
        for r in doc_data["risks"]:
            p.text(f"· {r}", size=10, color=C_TEXT, indent=10)
        p.gap(4)

    if doc_data.get("dimensions"):
        p.text("评估维度：" + "、".join(doc_data["dimensions"]), size=9, color=C_FAINT)

    p.rule()
    p.text(doc_data.get("generated_note") or "", size=8.5, color=C_FAINT)

    out = d.tobytes()
    d.close()
    return out
