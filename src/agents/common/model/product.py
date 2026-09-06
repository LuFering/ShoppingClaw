"""
商品领域模型（Day 1 扁平化设计）

设计说明（非实现细节）：
- 基础字段：跨平台统一的最小可比对集合，爬虫/Agent 写入时必填。
- 展示字段：列表卡片与对话摘要用，缺失时不影响核心逻辑。
- 业务字段：对比与推荐用弱结构化信息；specs 用字典承载平台差异参数。
"""

from __future__ import annotations

from typing import Dict, Literal, Optional

from pydantic import BaseModel, Field, field_validator, HttpUrl

PlatformCode = Literal["jd", "taobao", "pdd"]


class Product(BaseModel):
    """扁平化商品快照，供搜索/对比/推荐在各层传递。"""

    # --- 基础字段（必须）：统一主键与成交相关核心事实 ---
    id: str = Field(description="商品唯一标识，建议格式：{platform}_{平台侧ID}")
    title: str = Field(description="商品标题，用于展示与检索摘要")
    price: float = Field(gt=0, description="当前价格（人民币元），必须为正数")
    state: int = Field(description="商品状态（是否处在上架销售状态）")
    platform: PlatformCode = Field(description="来源平台：jd / taobao / pdd")
    # url: str = Field(description="商品详情页链接")

    url: HttpUrl = Field(description="商品详情页链接")
    image_url: Optional[HttpUrl] = Field(default=None, description="主图 URL")
    # --- 展示字段（可选）：列表与卡片层信息 ---
    # image_url: Optional[str] = Field(default=None, description="主图 URL")
    shop_name: Optional[str] = Field(default=None, description="店铺名称")
    rating: Optional[float] = Field(default=None, ge=0, le=5, description="评分，5 分制，缺省表示未知")
    comment_count: Optional[int] = Field(default=None, description="评论数")
    sales_count: Optional[int] = Field(default=None, description="销量（平台口径可能不同，仅存展示值）")

    delivery_address:Optional[str]=Field(default=None,description="发货地址")
    express_info: Optional[dict] = Field(default=None, description="物流信息（预计送达、运费说明）")
    after_sales_info: Optional[dict] = Field(default=None, description="售后保障信息（7天无理由、价保、破损包退等）")
    increment_service: Optional[dict] = Field(default=None, description="增值服务（产地、质保、特色服务）")
    promo_info: Optional[dict] = Field(default=None, description="促销信息（赠品、满减、优惠券）")
    rank_info: Optional[dict] = Field(default=None, description="排行榜信息（品类排名）")
    good_comment_keywords: Optional[list] = Field(default=None, description="好评关键词列表")
    installment_info: Optional[str] = Field(default=None, description="分期信息（如12期免息）")
    promo_tags: Optional[str] = Field(default=None, description="促销标签（如赠品、秒杀）")

    # --- 业务字段（可选）：弱结构化属性 ---
    category: Optional[str] = Field(default=None, description="类目路径或名称")
    brand: Optional[str] = Field(default=None, description="品牌")
    key_specs: Dict[str, str] = Field(
        default_factory=dict,
        description="规格参数键值对，适配不同品类",
    )
