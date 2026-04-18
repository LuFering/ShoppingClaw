import logging
from typing import Dict, Any

from src.agents.common.toolkits.registry import tool
from src.agents.common.toolkits.shopping.schemas import ProductSearchInput
from src.tools.search import search

logger = logging.getLogger(__name__)

# ==========================================
# 工具包装器 (Wrapper) - 骨架
# ==========================================
# 💡 解释：
# `@tool` 装饰器会自动把这个函数注册到 Agent 的可用工具列表里。
# `args_schema` 指定了我们刚刚在 schemas.py 里定义的输入模型，
# 这样 LangChain 就会在调用函数前，先用 Pydantic 校验大模型传来的参数。

@tool(
    category="shopping",
    tags=["搜索", "商品"],
    display_name="跨平台商品搜索",
    icon="🔍",
    args_schema=ProductSearchInput,
)
def product_search(query: str, platforms: list[str] | None = None, limit: int = 10) -> Dict[str, Any]:
    """
    跨平台搜索商品工具。
    
    职责：
    - 接收大模型传来的搜索请求
    - 校验参数并调用底层的 src/tools/search.py
    - 捕获异常，返回统一的字典结构 {"products": [...], "error": None}
    
    注意：
    大模型在调用工具时，如果不知道某项参数，可能会传默认值或者少传。
    我们需要在这个函数内部做好防御性编程（try-except）。
    """
    logger.info(f"[Tool] 执行商品搜索: query={query}, platforms={platforms}, limit={limit}")
    
    try:
        # 调用底层的业务逻辑
        results = search(query=query, platforms=platforms, limit=limit)
        return {"products": results, "error": None}
    except ValueError as ve:
        # 捕获已知的值错误（比如 query 为空，limit 越界）
        error_msg = f"参数错误: {str(ve)}"
        logger.warning(f"[Tool] 商品搜索参数错误: {error_msg}")
        return {"products": [], "error": error_msg}
    except Exception as e:
        # 捕获其他未知错误，防止 Agent 崩溃
        error_msg = f"执行搜索时发生未知错误: {str(e)}"
        logger.error(f"[Tool] 商品搜索未知错误: {error_msg}", exc_info=True)
        return {"products": [], "error": error_msg}
