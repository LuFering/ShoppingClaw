
"""
购物助手多 Agent 工作流状态定义（MVP）。

设计说明：
- ShoppingState 是 LangGraph 节点间传递的唯一数据载体。
- 入口只需 query + platform，其余字段由各节点逐步写入。
- 节点更新风格：node(state: ShoppingState) -> dict，只返回变更字段。
"""
from __future__ import annotations

from typing import List, Literal, Optional

from typing_extensions import NotRequired, TypedDict

from agents.common.model.product import Product

PlatformCode = Literal["jd", "taobao", "pdd"]


class ShoppingState(TypedDict):
    """LangGraph 工作流状态，贯穿全部节点。"""

    # --- 输入层：入口节点写入，后续节点只读 ---
    query: str                          # 用户搜索词
    platform: PlatformCode              # 来源平台，限定为 jd / taobao / pdd

    # --- 数据层：搜索 / 过滤 / 排序节点逐步写入 ---
    products: NotRequired[List[Product]]  # 中间商品列表
    analysis_report: NotRequired[str]     # 市场分析报告 (由 analysis_agent 写入)

    # --- 输出层：出口节点写入 ---
    recommendations: NotRequired[List[Product]]  # 最终推荐列表
    answer: NotRequired[str]                     # 自然语言回复

    # --- 控制层：任一节点报错时写入 ---
    error: NotRequired[Optional[str]]            # 错误信息



def build_shopping_state(query: str, platform: PlatformCode) -> ShoppingState:
    """
    构造最小可运行的初始 ShoppingState。

    在入口处统一填好默认值，避免节点内做防御性 .get() 判断。
    platform 的合法性由 PlatformCode 类型在静态检查阶段约束；
    如需运行时强校验，在调用此函数的 API 层用 Pydantic 校验入参。
    """
    return ShoppingState(
        query=query,
        platform=platform,
        products=[],
        recommendations=[],
        answer="",
        error=None,
    )
