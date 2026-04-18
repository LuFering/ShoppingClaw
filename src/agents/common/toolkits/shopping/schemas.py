from typing import List, Optional
from pydantic import BaseModel, Field

from src.models.product import Product

# ==========================================
# 统一返回结构 (字典形式)
# ==========================================
# 💡 解释：
# 工具最终返回给 Agent 的是 dict，而不是 Pydantic Model。
# 这是因为 LangChain/LangGraph 对 dict 的兼容性最好，而且将来序列化给前端也最方便。
# 我们在这里写注释，只是为了明确返回的结构长什么样。

# Search & Filter 工具的返回结构
# {
#     "products": List[Product],  # 成功时返回商品列表，失败时为空列表
#     "error": Optional[str]      # 成功时为 None，失败时为错误描述字符串
# }

# Compare 工具的返回结构
# {
#     "report": str,                  # 对比报告文本
#     "ranked_products": List[Product], # 排序后的商品列表
#     "error": Optional[str]          # 成功时为 None，失败时为错误描述字符串
# }


# ==========================================
# 输入参数结构 (Pydantic Models)
# ==========================================
# 💡 解释：
# 我们用 Pydantic 来严格校验工具的输入参数。
# 这样如果大模型传错了参数（比如把 limit 传成了 200），Pydantic 就会立刻报错。
# 我们的工具包装器（Wrapper）会捕获这个报错，然后优雅地把错误信息写进上面的 `error` 字段里，返回给 Agent。

class ProductSearchInput(BaseModel):
    """商品搜索工具的输入参数"""
    query: str = Field(description="用户搜索词，不能为空，长度不超过 100")
    platforms: Optional[List[str]] = Field(default=None, description="平台列表，为 None 表示全平台。可选值：jd, taobao, pdd")
    limit: int = Field(default=10, ge=1, le=100, description="每个平台返回的商品数量限制（1-100）")

class ProductFilterInput(BaseModel):
    """商品过滤工具的输入参数"""
    products: List[Product] = Field(description="需要过滤的商品列表")
    price_min: Optional[float] = Field(default=None, description="最低价格限制")
    price_max: Optional[float] = Field(default=None, description="最高价格限制")
    platforms: Optional[List[str]] = Field(default=None, description="指定平台列表（如['jd', 'taobao']）")
    min_rating: Optional[float] = Field(default=None, ge=0, le=5, description="最低评分限制（0-5）")
    brands: Optional[List[str]] = Field(default=None, description="指定品牌列表")
    keywords: Optional[List[str]] = Field(default=None, description="标题必须包含的关键词列表（OR逻辑，大小写不敏感）")

class ProductCompareInput(BaseModel):
    """商品对比工具的输入参数"""
    products: List[Product] = Field(description="需要对比的商品列表")
