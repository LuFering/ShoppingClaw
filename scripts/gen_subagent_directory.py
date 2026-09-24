"""从 subagents.yaml 生成「子智能体目录」知识库文档。

为什么用脚本生成而不是手写：
  这份目录是主智能体决定「该派谁」的依据，必须与 `subagents.yaml`
  **逐字一致**。手写必然漂移（改 yaml 忘了改文档），而漂移的后果是
  主智能体按过时信息派遣。

用法：
    python scripts/gen_subagent_directory.py

产出：docs/knowledge/subagent_directory/<slug>.md
灌库：重启 api 容器即可（KnowledgeManager 会在启动时加载新文档）

⚠️ 注意：`KnowledgeManager.initialize` 只在 Chroma 集合为空时灌入。
   已有集合时改文档不会自动生效，需先清空集合或删除 saves/knowledge/chroma。
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
YAML_PATH = REPO / "src" / "agents" / "subagents" / "subagents.yaml"
OUT_DIR = REPO / "docs" / "knowledge" / "subagent_directory"

# 中文展示名（与 orchestration_composer.display_name 保持一致）
DISPLAY = {
    "pre_purchase": "购前助手",
    "post_purchase": "购后助手",
}

# 「不做什么」—— 路由的关键（反路由字段），防止误派。
# 与各自 system_prompt 的「边界 / 严格禁止」段落对应，改 prompt 时同步这里。
NOT_FOR = {
    "pre_purchase": "不归档、不下单、不查物流、不做用户画像分析",
    "post_purchase": (
        "不搜新商品、不做商品对比、不出推荐卡、不评价商品；"
        "不碰订单 / 物流 / 售后 / 支付"
    ),
}

# 触发意图 —— 决定「什么话该派它」
TRIGGERS = {
    "pre_purchase": [
        "挑选商品",
        "多款对比",
        "比价",
        "值不值得买",
        "找货 / 要推荐",
    ],
    "post_purchase": [
        "已决定购买 / 已下单 / 已收货",
        "表达可长期复用的偏好（品牌、预算、使用场景）",
        "要求提醒（比价、降价、保修到期、收货确认）",
        "想先记下来 / 以后再说",
        "要写使用反馈或复盘",
    ],
}

# 交付产物
DELIVERS = {
    "pre_purchase": "结构化候选（picks：sku_id / title / price / platform / url）",
    "post_purchase": "购物档案条目（归档 / 阶段推进 / 提醒 / 复盘）",
}


def _render(slug: str, spec: dict) -> str:
    name = DISPLAY.get(slug, slug)
    desc = (spec.get("description") or "").strip()
    tools = spec.get("tools") or []
    model = spec.get("model") or "(继承主智能体)"

    lines = [
        "---",
        "source_type: framework",
        f"doc_id: subagent_{slug}",
        "category: 子智能体目录",
        f"tags: {slug},{name},路由,派遣",
        f"keywords: {slug},{name},派遣,路由,该派谁",
        f"title: {name}",
        "---",
        "",
        f"# {name}（{slug}）",
        "",
        "## 能做什么",
        "",
        desc or "（未填写）",
        "",
        "## 不能做什么",
        "",
        NOT_FOR.get(slug, "（未填写）"),
        "",
        "## 什么情况该派它",
        "",
    ]
    for t in TRIGGERS.get(slug, []):
        lines.append(f"- {t}")

    lines += [
        "",
        "## 交付什么",
        "",
        DELIVERS.get(slug, "（未填写）"),
        "",
        "## 可用工具",
        "",
    ]
    for t in tools:
        lines.append(f"- `{t}`")

    lines += [
        "",
        "## 如何派遣",
        "",
        f"- 通过 `task` 工具调用，`subagent_type=\"{slug}\"`",
        f"- 模型：`{model}`",
        "",
    ]
    return "\n".join(lines)


def main() -> int:
    if not YAML_PATH.exists():
        print(f"找不到 {YAML_PATH}", file=sys.stderr)
        return 1

    cfg = yaml.safe_load(YAML_PATH.read_text(encoding="utf-8"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for slug, spec in cfg.items():
        out = OUT_DIR / f"{slug}.md"
        out.write_text(_render(slug, spec), encoding="utf-8")
        print(f"已生成 {out.relative_to(REPO)}")

    print(f"\n共 {len(cfg)} 个文件")
    print("提示：若 Chroma 集合非空，需先清空才能重新灌入（见脚本 docstring）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
