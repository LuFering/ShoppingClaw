from typing import Optional, List, Literal

from pydantic import BaseModel, Field

urgency=Literal["immediate", "within_week", "flexible"]
dimensions=List["price", "performance"]

class UserProfile(BaseModel):
    budget_limit: Optional[float]=Field(default=None,description="最低预算")
    budget_max: Optional[float]=Field(default=None,description="最高预算")

    delivery_urgency:Optional[urgency]=Field(default="flexible",description="配送急迫度")
    location_context:Optional[str]=Field(default=None,description="用户地址")

    preferred_brands: List[str]=Field(description="偏好品牌白名单")
    forbidden_brands: List[str]=Field(description="品牌黑名单")
    # 动态权重：针对当前话题的偏好
    focus_dimensions: List[dimensions] =Field(description="关注维度")
