"""post_purchase 契约测试（优化方案阶段一：工具绑定 + schema 感知降级）

覆盖点：
1. subagents.yaml 的 post_purchase 工具绑定 = 4 个既有的记忆工具
2. 绑定中不含任何购前搜索 / 商品类工具（边界不越权）
3. YAML prompt 保持购后边界文案，并包含工具使用指引
4. discovery.filter_by_agent 与 YAML 逐字一致（防配置漂移）
5. chat_stream_service._SUBAGENT_PLANNED_TOOLS 第三处镜像一致
6. _insufficient_data_fallback 按 schema 降级：post_purchase 返回合法空
   MemoryOutput；pre_purchase 沿用 insufficient_data 形状
7. _validate_output 对 post_purchase 的合法 / 非JSON / 越权（购前形状）输入
   行为正确

按仓库既有测试风格实现为可独立运行的脚本（python test/xxx.py），
同时 test_* 函数可被 pytest 收集。设计为在 api 容器内运行
（sys.path 已指向 /app，依赖齐全）。
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, "/app")

import yaml

REPO = Path(__file__).resolve().parent.parent
POST_TOOLS = [
    "get_user_shopping_context",
    "save_user_preference",
    "recall_past_decisions",
    "get_user_profile",
]
FORBIDDEN_PRE_TOOLS = {
    "search_products",
    "get_product_full_detail",
    "get_products_specs_batch",
    "get_products_specs_extract",
    "filter_products_by_criteria",
}


def _load_yaml() -> dict:
    return yaml.safe_load(
        (REPO / "src" / "agents" / "subagents" / "subagents.yaml").read_text(encoding="utf-8")
    )


def test_yaml_tool_binding() -> None:
    cfg = _load_yaml()["post_purchase"]
    assert list(cfg["tools"]) == POST_TOOLS, f"YAML 工具绑定不符: {cfg['tools']}"


def test_yaml_no_pre_purchase_tools() -> None:
    tools = set(_load_yaml()["post_purchase"]["tools"])
    overlap = tools & FORBIDDEN_PRE_TOOLS
    assert not overlap, f"购后助手不得绑定购前工具: {overlap}"


def test_yaml_prompt_boundary_and_tools() -> None:
    prompt = _load_yaml()["post_purchase"]["system_prompt"]
    assert "不搜索新商品" in prompt
    assert "不出推荐卡" in prompt
    assert "get_user_shopping_context" in prompt
    assert "save_user_preference" in prompt
    # 推断信号不落库的约束必须写进 prompt
    assert "推断" in prompt and "save_user_preference" in prompt


def test_discovery_binding_matches_yaml() -> None:
    from src.agents.common.toolkits.discovery import filter_by_agent

    tools = filter_by_agent("post_purchase")
    assert sorted(t.name for t in tools) == sorted(POST_TOOLS), (
        f"discovery 与 YAML 漂移: {[t.name for t in tools]}"
    )


def test_planned_tools_mirror() -> None:
    from src.services.chat_stream_service import _SUBAGENT_PLANNED_TOOLS

    assert list(_SUBAGENT_PLANNED_TOOLS["post_purchase"]) == POST_TOOLS


def test_fallback_is_schema_aware() -> None:
    from src.agents.common.middleware.subagents import _insufficient_data_fallback
    from src.agents.common.model import MemoryOutput

    post = json.loads(_insufficient_data_fallback("post_purchase"))
    out = MemoryOutput.model_validate(post)  # 形状不符会直接抛异常
    assert out.data.new_signals == []
    assert out.data.profile_updated is False
    assert out.evidence_type == "user_preference"

    pre = json.loads(_insufficient_data_fallback("pre_purchase"))
    assert pre["evidence_type"] == "insufficient_data"
    assert pre["data"]["picks"] == []


def test_validate_output_contract() -> None:
    from src.agents.common.middleware.subagents import _validate_output

    valid = json.dumps(
        {
            "evidence_type": "user_preference",
            "data": {
                "relevant_preferences": {"brand_preference": "小米"},
                "new_signals": [
                    {
                        "field": "brand_preference",
                        "value": "小米",
                        "signal_type": "explicit",
                        "basis": "用户原话：只买小米的",
                    }
                ],
            },
            "summary": "用户明确偏好小米品牌。",
        },
        ensure_ascii=False,
    )
    ok, payload = _validate_output("post_purchase", valid)
    assert ok, f"合法 MemoryOutput 校验失败: {payload}"
    assert json.loads(payload)["data"]["new_signals"]

    ok2, _ = _validate_output("post_purchase", "这不是 JSON")
    assert not ok2, "非 JSON 输入应校验失败"

    pre_shaped = json.dumps(
        {
            "evidence_type": "presales_recommendation",
            "summary": "x",
            "data": {
                "picks": [],
                "tradeoffs": [],
                "risks": [],
                "rejected": [],
                "no_recommendation_reason": None,
            },
        }
    )
    ok3, _ = _validate_output("post_purchase", pre_shaped)
    assert not ok3, "购前形状的载荷不应通过 MemoryOutput 校验"


def main() -> None:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for t in tests:
        t()
        print(f"PASS {t.__name__}")
    print(f"\n{len(tests)} contract tests passed")


if __name__ == "__main__":
    main()
