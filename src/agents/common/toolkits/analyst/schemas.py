from pydantic import BaseModel, Field
from typing import List, Optional

class GetProductsSpecsInput(BaseModel):
    """批量获取商品规格参数的输入模型"""
    products: List[dict] = Field(
        ..., 
        description="待分析的商品列表，每个元素应包含 id, title, price 等基础信息"
    )

class FilterProductsInput(BaseModel):
    """基于硬性条件过滤商品的输入模型"""
    products: List[dict] = Field(
        ..., 
        description="原始商品列表"
    )
    max_price: Optional[float] = Field(
        None, 
        description="最高限价，超过此价格的商品将被剔除"
    )
    min_rating: Optional[float] = Field(
        None, 
        description="最低评分要求（0-5分），低于此评分的商品将被剔除"
    )
    required_brands: Optional[List[str]] = Field(
        None, 
        description="必须包含的品牌名称列表，不在列表中的品牌将被剔除"
    )
    exclude_keywords: Optional[List[str]] = Field(
        None, 
        description="标题中不能出现的关键词列表，包含任一关键词的商品将被剔除"
    )

class QueryKnowledgeInput(BaseModel):
    """检索品类决策知识的输入模型"""
    category: str = Field(
        ..., 
        description="商品品类名称，例如：智能手机、游戏本、降噪耳机"
    )
    focus_area: Optional[str] = Field(
        None, 
        description="可选的关注点，用于精准检索特定维度的知识，例如：屏幕素质、续航能力、售后服务"
    )
