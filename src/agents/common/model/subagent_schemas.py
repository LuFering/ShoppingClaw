from pydantic import BaseModel, Field, field_validator
from typing import List, Optional, Any, Literal, Union, Dict
from src.agents.common.model.product import Product

PlatformCode = Literal["jd", "taobao", "pdd"]


class ProductCardSnapshot(BaseModel):
    """商品卡片快照 —— 交付 UI 卡片的最小字段集。

    与 `Product` 的区别（有意为之）：
      · 不带 `state`。搜索工具 `search_products` 从不返回该字段，
        强制要求它会让每次校验都失败。
      · `url` 可空。它只来自 Justone 的 landUrl，官方 API 路径下常缺失。
        缺失时下发 null，前端回退为不可点击 —— 绝不编造 `#` 或假链接。
      · 缺少稳定 sku_id 或价格的商品**不允许**进入这里：宁可少出卡，
        也不能伪造一张完整的卡。
    """
    sku_id: str = Field(..., min_length=1, description="商品唯一标识（工具返回的 id 去掉平台前缀，如 jd_123 → 123）")
    title: str = Field(..., min_length=1, description="商品标题")
    price: float = Field(..., gt=0, description="到手价（人民币元），必须为正数")
    platform: PlatformCode = Field(..., description="来源平台编码：jd / taobao / pdd")
    url: Optional[str] = Field(default=None, description="商品详情页链接；工具未返回时为 null")
    image_url: Optional[str] = Field(default=None, description="主图 URL")
    rating: Optional[float] = Field(default=None, ge=0, le=5, description="评分，5 分制")
    shop_name: Optional[str] = Field(default=None, description="店铺名称")


class TradeoffItem(BaseModel):
    """单款为什么入选 / 为什么不选。"""
    sku_id: str = Field(..., description="对应的商品唯一标识")
    verdict: str = Field(..., description="入选 (pick) | 排除 (reject)")
    reason: str = Field(..., description="一句话说明：为什么选它 / 为什么排除")


class RejectedItem(BaseModel):
    """明确排除项。"""
    sku_id: Optional[str] = Field(default=None, description="被排除商品标识；无稳定 id 时为 null")
    title: Optional[str] = Field(default=None, description="被排除商品标题，便于用户理解")
    reason: str = Field(..., description="排除原因（不满足哪条硬约束）")


class PrePurchaseData(BaseModel):
    """购前助手输出的数据结构化封装。所有字段必须源自工具返回的真实快照。"""
    picks: List[ProductCardSnapshot] = Field(
        default_factory=list,
        description="最终推荐候选，保留完整商品快照。无合适结果时留空，并填 no_recommendation_reason。",
    )
    tradeoffs: List[TradeoffItem] = Field(default_factory=list, description="每款入选 / 不选的取舍理由")
    risks: List[str] = Field(default_factory=list, description="风险或待确认项（售后、正品、长期成本等）")
    rejected: List[RejectedItem] = Field(default_factory=list, description="被明确排除的商品与原因")
    no_recommendation_reason: Optional[str] = Field(
        default=None,
        description="无合适结果时说明共性缺陷；有 picks 时为 null。",
    )


class PrePurchaseOutput(BaseModel):
    """购前助手的统一输出协议。只返回此结构的 JSON，不要 Markdown 或解释文字。

    交付路径：本协议只承载结构化候选，**不出卡**。
    卡片由 runtime 在 task 块内根据 picks 合成，保证字段不被二次抽取。
    """
    evidence_type: str = Field(default="presales_recommendation", description="证据类型标签，固定为 presales_recommendation")
    data: PrePurchaseData
    summary: str = Field(..., description="一句话核心结论：推了哪几款、关键取舍是什么；无推荐则说明原因")


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
    # 2026-09-22：原为 dict，但模型实际常输出**列表**
    # （[{'dimension': 'brand_preference', 'value': ...}, ...]），
    # 严格校验失败会导致整轮结论降级作废。这里放宽为二者皆可，
    # 再由下面的校验器归一成 dict，下游契约不变。
    relevant_preferences: Union[Dict[str, Any], List[Any]] = Field(
        ..., description="与当前任务相关的历史偏好摘要（键值对形式，也接受条目列表）"
    )

    @field_validator("relevant_preferences")
    @classmethod
    def _normalize_preferences(cls, v):
        """列表形态归一成 {dimension: value} 字典。

        条目里能取到 dimension/value 就按这对建键；取不到时退化用
        field / key / index 兜底，保证不因单条格式特殊而整轮失败。
        """
        if isinstance(v, dict):
            return v
        if not isinstance(v, list):
            return v
        out: Dict[str, Any] = {}
        for i, item in enumerate(v):
            if isinstance(item, dict):
                key = (
                    item.get("dimension")
                    or item.get("field")
                    or item.get("key")
                    or item.get("name")
                    or f"pref_{i}"
                )
                out[str(key)] = item.get("value", item)
            else:
                out[f"pref_{i}"] = item
        return out
    preference_insights: Optional[str] = Field(None, description="基于画像的深度洞察：这些偏好如何影响当前的推荐策略")
    new_signals: List[PreferenceSignal] = Field(default_factory=list, description="本轮对话中提取的新增或更新信号")
    profile_updated: bool = Field(default=False, description="是否触发了用户画像的实质性更新")
    conflicts_detected: Optional[str] = Field(None, description="如有偏好冲突，简要说明（无冲突则 null）")

class MemoryOutput(BaseModel):
    """Memory Manager Agent 的统一输出协议"""
    evidence_type: str = Field(default="user_preference", description="证据类型标签，固定为 user_preference")
    data: MemoryData
    summary: str = Field(..., description="一句话总结：用户的核心特征及本轮最重要的个性化参数")
