from typing import List, Dict, Optional
from pydantic import BaseModel, Field

class GroupingStrategy(BaseModel):
    """分组策略定义"""
    dimension: str = Field(description="分组维度，如'price_tier', 'performance_level', 'style'")
    group_names: List[str] = Field(description="预设的组名，如['基础款', '均衡款', '旗舰款']")
    criteria_per_group: Dict[str, dict] = Field(description="每组的筛选标准，如{'旗舰款': {'min_price': 4000}}")

class EliminationRules(BaseModel):
    """淘汰赛规则"""
    hard_constraints: List[str] = Field(default=[], description="硬性淘汰项，如'无礼盒包装', '库存<10'")
    risk_thresholds: Dict[str, float] = Field(
        default={"bad_review_rate": 0.05, "return_rate": 0.1}, 
        description="风险阈值，超过即淘汰"
    )

class ScoringCriteria(BaseModel):
    """分析师的深度决策标准"""
    
    # --- 需求特征建模 (来自 Memory/Intent) ---
    demand_vector: Dict[str, float] = Field(description="需求权重向量，如{'ritual_sense': 0.9, 'practicality': 0.4}")
    
    # --- 分组策略 ---
    grouping_strategy: Optional[GroupingStrategy] = Field(default=None, description="如何对商品进行分组呈现")
    
    # --- 淘汰规则 (先过滤再打分) ---
    elimination_rules: EliminationRules = Field(default_factory=EliminationRules)
    
    # --- 评分维度 (针对组内优胜者) ---
    scoring_dimensions: Dict[str, float] = Field(
        default={"specs": 0.4, "sentiment": 0.3, "service": 0.2, "value": 0.1},
        description="各维度的评分权重"
    )

class ScoredProduct(BaseModel):
    """带评分的商品信息"""
    product_id: str
    group_name: str
    total_score: float
    dimension_scores: Dict[str, float]
    recommendation_reason: str
    is_winner: bool = False
