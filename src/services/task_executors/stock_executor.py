"""
库存监控执行器

搜索商品 → 检测库存状态变化 → 到货时触发提醒
"""
import logging

from src.storage.postgres.models_business import TaskRecord
from src.services.mcp_service import call_stdio_tool_async, MCP_SERVERS
from src.services.task_executors.common import parse_search_result

logger = logging.getLogger(__name__)

# 内存中记录上次库存状态（服务重启会丢失，生产应存 Redis）
_last_stock_status: dict[str, str] = {}


async def execute(task: TaskRecord) -> dict:
    """
    task_params: {"product_name": "...", "platform": "taobao"}
    """
    params = task.task_params or {}
    product_name = params.get("product_name", "")
    platform = params.get("platform", "taobao")

    if not product_name:
        return {"error": "缺少 product_name 参数"}

    raw = await call_stdio_tool_async(
        "taobao_mcp", MCP_SERVERS.get("taobao_mcp", {}),
        "taobao.searchMaterial",
        {"q": product_name, "page_size": 3}
    )

    products = parse_search_result(raw)
    if not products:
        return {"status": "no_results", "product_name": product_name}

    matched = products[0]
    title = matched.get("title", product_name)
    product_id = str(matched.get("item_id", ""))
    in_stock = _check_stock(matched)

    prev_status = _last_stock_status.get(product_id, "unknown")
    _last_stock_status[product_id] = in_stock

    result = {
        "status": "ok",
        "product_name": title,
        "product_id": product_id,
        "stock_status": in_stock,
    }

    if prev_status == "out_of_stock" and in_stock == "in_stock":
        result["alert"] = f"{title} 已到货！"
        result["triggered"] = True
    elif prev_status == "in_stock" and in_stock == "out_of_stock":
        result["alert"] = f"{title} 已缺货"
        result["triggered"] = True
    else:
        result["triggered"] = False

    return result


def _check_stock(product: dict) -> str:
    """判断库存状态"""
    stock = product.get("stock", product.get("stock_status", ""))
    stock_str = str(stock).lower()
    if stock_str in ("1", "true", "in_stock", "有货"):
        return "in_stock"
    if stock_str in ("0", "false", "out_of_stock", "无货", "缺货"):
        return "out_of_stock"
    return "unknown"
