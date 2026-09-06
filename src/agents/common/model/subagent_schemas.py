from pydantic import BaseModel, Field
from typing import List, Optional, Any
from agents.common.model.product import Product

class ResearcherData(BaseModel):
    """Researcher 输出的数据结构化封装。请确保所有数据均源自工具调用结果。"""
    products: List[Product] = Field(..., description="商品列表。**关键约束**：仅填充工具实际返回的字段。若工具未提供 shop_name 或 good_rate，请留空或设为 null，严禁根据品牌常识进行脑补。")
    data_source: str = Field(default="官方API", description="数据来源标识，例如 '京东官方API'")
    coverage_note: Optional[str] = Field(None, description="简要说明本次搜索覆盖的关键词维度")

class ResearcherOutput(BaseModel):
    """Researcher Agent 的统一输出协议。请直接返回此结构的 JSON 对象，不要包含任何 Markdown 标记或解释性文字。"""
    evidence_type: str = Field(default="product_list", description="证据类型标签，固定为 product_list")
    data: ResearcherData
    summary: str = Field(..., description="一句话核心结论。必须基于上述 products 中的真实数据总结，不得包含未在列表中出现的商品信息。")

# ------------------------------------------------------------
# Analyst Agent Schemas
# ------------------------------------------------------------
class DimensionScore(BaseModel):
    """维度评分模型"""
    dimension: str = Field(..., description="评估维度名称，如：性能、续航、影像")
    score: float = Field(..., ge=0, le=10, description="0-10分的量化评分")
    reasoning: str = Field(..., description="简短的评分理由，将参数翻译成体验语言")

class AnalystProductItem(BaseModel):
    """分析师视角的商品条目"""
    id: str = Field(..., description="商品唯一标识")
    title: str = Field(..., description="商品标题")
    scores: List[DimensionScore] = Field(..., description="各维度的详细评分与理由")
    best_for: str = Field(..., description="最适合哪类用户或场景（一句话）")
    watch_out: Optional[str] = Field(None, description="最值得注意的短板或劝退点")

class AnalystData(BaseModel):
    """Analyst 输出的数据结构化封装"""
    analysis_mode: str = Field(..., description="分析模式：comparison | single_analysis | no_good_option")
    key_decision_factors: List[str] = Field(..., description="本次决策最关键的2-3个因素")
    products: List[AnalystProductItem]
    recommendation: Optional[str] = Field(None, description="最终推荐的商品ID，若无明显优胜者则为 null")

class AnalystOutput(BaseModel):
    """Analyst Agent 的统一输出协议"""
    evidence_type: str = Field(default="comparison_matrix", description="证据类型标签，固定为 comparison_matrix")
    data: AnalystData
    summary: str = Field(..., description="一句话核心结论：谁胜出、胜在哪里，或为什么没有明显推荐")

# ------------------------------------------------------------
# Critic Agent Schemas
# ------------------------------------------------------------
class RiskItem(BaseModel):
    """风险项模型"""
    item_id: Optional[str] = Field(None, description="涉及的商品ID，整体风险则为 null")
    dimension: str = Field(..., description="风险维度，如：预算完整性、售后政策")
    level: str = Field(..., description="风险等级：red (红线) | yellow (警示) | acceptable (可接受)")
    description: str = Field(..., description="风险描述：是什么，为什么，对用户的实际影响")
    basis: str = Field(..., description="判断依据：evidence_based (有数据支撑) | experience_based (经验推断)")

class CriticData(BaseModel):
    """Critic 输出的数据结构化封装"""
    risks: List[RiskItem] = Field(..., description="识别出的风险列表")
    overall_verdict: str = Field(..., description="整体风险水位：safe | caution | risky")
    key_concern: Optional[str] = Field(None, description="如果只提醒一件事，最值得说的是什么")

class CriticOutput(BaseModel):
    """Critic Agent 的统一输出协议"""
    evidence_type: str = Field(default="risk_report", description="证据类型标签，固定为 risk_report")
    data: CriticData
    summary: str = Field(..., description="一句话整体风险水位及核心建议")

# ------------------------------------------------------------
# Memory Manager Agent Schemas
# ------------------------------------------------------------
class PreferenceSignal(BaseModel):
    """用户偏好信号模型"""
    field: str = Field(..., description="涉及的偏好字段，如 brand_preference, price_ceiling")
    value: Any = Field(..., description="提取到的具体偏好值")
    signal_type: str = Field(..., description="信号类型：explicit (用户明确表达) | inferred (基于语境推断)")
    basis: str = Field(..., description="判断依据：用户原话摘录或逻辑推导过程")

class MemoryData(BaseModel):
    """Memory 输出的数据结构化封装"""
    relevant_preferences: dict = Field(..., description="与当前任务相关的历史偏好摘要（键值对形式）")
    preference_insights: Optional[str] = Field(None, description="基于画像的深度洞察：这些偏好如何影响当前的推荐策略")
    new_signals: List[PreferenceSignal] = Field(default_factory=list, description="本轮对话中提取的新增或更新信号")
    profile_updated: bool = Field(default=False, description="是否触发了用户画像的实质性更新")
    conflicts_detected: Optional[str] = Field(None, description="如有偏好冲突，简要说明（无冲突则 null）")

class MemoryOutput(BaseModel):
    """Memory Manager Agent 的统一输出协议"""
    evidence_type: str = Field(default="user_preference", description="证据类型标签，固定为 user_preference")
    data: MemoryData
    summary: str = Field(..., description="一句话总结：用户的核心特征及本轮最重要的个性化参数")
