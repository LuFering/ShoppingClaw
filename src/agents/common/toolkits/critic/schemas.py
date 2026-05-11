from pydantic import BaseModel, Field
from typing import Optional, Literal


class QueryRiskPolicyInput(BaseModel):
    """检索平台风控规则的输入模型"""
    product_name: str = Field(
        ..., 
        description="商品名称或型号，例如：iPhone 15 Pro、联想拯救者Y9000P"
    )
    category: str = Field(
        ..., 
        description="商品品类，例如：智能手机、游戏本、蓝牙耳机"
    )
    risk_type: Optional[Literal["authenticity", "after_sales", "price_fraud", "quality"]] = Field(
        None, 
        description="风险类型（可选）：authenticity=正品验证, after_sales=售后政策, price_fraud=价格欺诈, quality=质量缺陷"
    )
