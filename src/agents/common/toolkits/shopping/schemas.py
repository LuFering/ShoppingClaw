from typing import List, Optional

from pydantic import BaseModel, Field

from src.models.product import PlatformCode, Product


class ProductSearchInput(BaseModel):
    query: str = Field(description="用户搜索词，不能为空，长度不超过 100")
    platforms: Optional[List[str]] = Field(default=None, description="平台列表，为 None 表示全平台。可选值：jd, taobao, pdd")
    limit: int = Field(default=10, ge=1, description="返回商品数量限制（>=1，越界由工具内部返回 error）")


class ProductFilterInput(BaseModel):
    products: List[Product] = Field(description="需要过滤的商品列表")
    price_min: Optional[float] = Field(default=None, description="最低价格限制")
    price_max: Optional[float] = Field(default=None, description="最高价格限制")
    platforms: Optional[List[PlatformCode]] = Field(default=None, description="指定平台列表（如['jd', 'taobao']）")
    min_rating: Optional[float] = Field(default=None, ge=0, le=5, description="最低评分限制（0-5）")
    brands: Optional[List[str]] = Field(default=None, description="指定品牌列表")
    keywords: Optional[List[str]] = Field(default=None, description="标题必须包含的关键词列表（OR逻辑，大小写不敏感）")


class ProductCompareInput(BaseModel):
    products: List[Product] = Field(description="需要对比的商品列表")
