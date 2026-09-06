"""
搜索排名监控执行器

搜索关键词 → 定位目标商品在结果中的位置 → 排名变化告警
"""
import logging

from src.storage.postgres.models_business import TaskRecord
from src.services.mcp_service import call_stdio_tool_async, MCP_SERVERS
from src.services.task_executors.common import parse_search_result

logger = logging.getLogger(__name__)

# 内存中记录上次排名
_last_ranks: dict[str, int] = {}


async def execute(task: TaskRecord) -> dict:
    """
    task_params:
        {
            "keyword": "蓝牙耳机",
            "product_name": "小米Air2 SE",   # 要跟踪排名的商品
            "platform": "taobao"
        }
    """
    params = task.task_params or {}
    keyword = params.get("keyword", "")
    product_name = params.get("product_name", "")
    platform = params.get("platform", "taobao")

    if not keyword or not product_name:
        return {"error": "缺少 keyword 或 product_name 参数"}

    raw = await call_stdio_tool_async(
        "taobao_mcp", MCP_SERVERS.get("taobao_mcp", {}),
        "taobao.searchMaterial",
        {"q": keyword, "page_size": 20}
    )

    products = parse_search_result(raw)
    if not products:
        return {"status": "no_results", "keyword": keyword}

    # 查找目标商品的排名位置
    rank = None
    product_name_lower = product_name.lower()
    for i, p in enumerate(products):
        title = str(p.get("title", "")).lower()
        if product_name_lower in title:
            rank = i + 1
            break

    rank_key = f"{keyword}:{product_name}"
    prev_rank = _last_ranks.get(rank_key)
    _last_ranks[rank_key] = rank

    result = {
        "status": "ok",
        "keyword": keyword,
        "product_name": product_name,
        "current_rank": rank,
        "total_results": len(products),
    }

    if rank is None:
        result["alert"] = f"{product_name} 未在关键词「{keyword}」搜索结果中出现"
        result["triggered"] = True
    elif prev_rank is not None:
        change = prev_rank - rank
        if change > 0:
            result["alert"] = f"排名上升 {change} 位！从第 {prev_rank} 升至第 {rank}"
            result["rank_change"] = change
            result["triggered"] = abs(change) >= 3
        elif change < 0:
            result["alert"] = f"排名下降 {abs(change)} 位，从第 {prev_rank} 降至第 {rank}"
            result["rank_change"] = change
            result["triggered"] = abs(change) >= 3
        else:
            result["alert"] = "排名未变化"
            result["rank_change"] = 0
            result["triggered"] = False

    if prev_rank is None:
        # 首次监控，无比较基准
        result["alert"] = f"首次监控，当前排名第 {rank}" if rank else "首次监控，未上榜"
        result["triggered"] = False

    return result
