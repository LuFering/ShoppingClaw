"""MCP Server: jd_product_mcp — 京东商品搜索与详情查询。

本地 MCP Server，无需独立进程。通过项目现有京东 SDK + JustoneAPI
封装商品搜索、详情、图片、店铺可靠性等工具。
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# ── Tool Specs（MCP 协议的工具描述） ──

JD_PRODUCT_MCP_TOOLS: list[dict[str, Any]] = [
    {
        "name": "mcp_jd_search_products",
        "description": (
            "搜索京东商品，整合官方API（好评率、店铺ID）和JustoneAPI（价格、销量、服务保障）。"
            "参数：keyword（搜索关键词，必填）, page（页码，默认1），need_price（是否需要价格，默认true）。"
            "返回结构化商品列表：id, title, price, platform, shop_name, sales_count等。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "keyword": {"type": "string", "description": "搜索关键词，如 'iPhone 15'"},
                "page": {"type": "integer", "description": "页码，默认1"},
                "need_price": {"type": "boolean", "description": "是否需要价格信息，默认true"},
            },
            "required": ["keyword"],
        },
    },
    {
        "name": "mcp_jd_product_detail",
        "description": (
            "获取京东商品详细信息（价格、库存、规格、品牌、运费、评价数、服务保障）。"
            "参数：sku_id（商品SKU ID，字符串，必填）。"
            "返回完整商品详情JSON。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sku_id": {"type": "string", "description": "商品SKU ID，如 '100012345678'"},
            },
            "required": ["sku_id"],
        },
    },
    {
        "name": "mcp_jd_product_images",
        "description": (
            "获取京东商品的主图和详情图列表。"
            "参数：sku_ids（商品SKU ID列表，如 ['100012345678', '100087654321']）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "sku_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "商品SKU ID列表",
                },
            },
            "required": ["sku_ids"],
        },
    },
    {
        "name": "mcp_jd_shop_reliability",
        "description": (
            "查询京东店铺可靠性（店铺评分、物流评分、服务评分、开店时长）。"
            "参数：shop_id（店铺ID，字符串，必填）。"
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "shop_id": {"type": "string", "description": "店铺ID"},
            },
            "required": ["shop_id"],
        },
    },
]


# ── Local Executors（本地执行器，直接调用 JD SDK / JustoneAPI） ──


def _exec_search_products(keyword: str, page: int = 1, need_price: bool = True) -> dict[str, Any]:
    """本地执行：搜索商品（整合官方 + Justone）。"""
    logger.info("[JD MCP] search_products: keyword=%s, page=%d", keyword, page)

    # 复用 tools.py 中已有逻辑（避免重复实现）
    try:
        from src.agents.common.toolkits.research.tools import search_products
        return search_products(keyword=keyword, page=page, need_price=need_price)
    except Exception as exc:
        logger.error("[JD MCP] search_products failed: %s", exc)
        return {"error": str(exc), "products": []}


def _exec_product_detail(sku_id: str) -> dict[str, Any]:
    """本地执行：商品详情。"""
    logger.info("[JD MCP] product_detail: sku_id=%s", sku_id)

    try:
        from src.agents.common.toolkits.research.tools import get_product_full_detail
        return get_product_full_detail(sku_id=sku_id)
    except Exception as exc:
        logger.error("[JD MCP] product_detail failed: %s", exc)
        return {"error": str(exc)}


def _exec_product_images(sku_ids: list[str]) -> dict[str, Any]:
    """本地执行：商品图片。"""
    logger.info("[JD MCP] product_images: sku_ids=%s", sku_ids)

    try:
        from src.agents.common.toolkits.research.tools import jd_product_images
        return jd_product_images(sku_ids=sku_ids)
    except Exception as exc:
        logger.error("[JD MCP] product_images failed: %s", exc)
        return {"error": str(exc)}


def _exec_shop_reliability(shop_id: str) -> dict[str, Any]:
    """本地执行：店铺可靠性。"""
    logger.info("[JD MCP] shop_reliability: shop_id=%s", shop_id)

    try:
        from src.agents.common.toolkits.research.tools import jd_shop_reliability
        return jd_shop_reliability(shop_id=shop_id)
    except Exception as exc:
        logger.error("[JD MCP] shop_reliability failed: %s", exc)
        return {"error": str(exc)}


# ── Dispatcher ──

JD_MCP_EXECUTORS: dict[str, Any] = {
    "mcp_jd_search_products": _exec_search_products,
    "mcp_jd_product_detail": _exec_product_detail,
    "mcp_jd_product_images": _exec_product_images,
    "mcp_jd_shop_reliability": _exec_shop_reliability,
}


def get_jd_mcp_tool_specs(server_name: str) -> list[dict[str, Any]]:
    """返回 jd_product_mcp 服务器的工具描述列表。

    每个 spec 注入 _mcp_server_name 和 _mcp_server_type="local"，
    供 mcp_tool_adapter 识别为本地执行模式。
    """
    specs: list[dict[str, Any]] = []
    for spec in JD_PRODUCT_MCP_TOOLS:
        spec_copy = dict(spec)
        spec_copy["_mcp_server_name"] = server_name
        spec_copy["_mcp_server_type"] = "local"  # 标记为本地执行
        spec_copy["_mcp_server_url"] = ""         # 本地模式无需 URL
        specs.append(spec_copy)
    return specs


def exec_jd_mcp_tool(tool_name: str, **kwargs: Any) -> Any:
    """执行京东 MCP 工具（由 mcp_tool_adapter 调度）。"""
    executor = JD_MCP_EXECUTORS.get(tool_name)
    if executor is None:
        return {"error": f"Unknown JD MCP tool: {tool_name}"}
    try:
        return executor(**kwargs)
    except Exception as exc:
        logger.error("[JD MCP] Tool %s execution failed: %s", tool_name, exc)
        return {"error": str(exc)}
