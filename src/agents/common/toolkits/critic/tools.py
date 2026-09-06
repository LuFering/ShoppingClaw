import logging
from typing import Optional

from src.agents.common.toolkits.registry import tool
from src.knowledge.manager import knowledge_manager
from .schemas import QueryRiskPolicyInput

logger = logging.getLogger(__name__)


@tool(
    category="critic",
    tags=["风控", "政策", "售后", "正品"],
    display_name="检索平台风控规则",
    icon="🛡️",
    args_schema=QueryRiskPolicyInput,
)
async def query_risk_policy(
    product_name: str,
    category: str,
    risk_type: Optional[str] = None,
) -> str:
    """
    为 Critic 提供特定品类/商品的风控政策和售后规则。
    
    职责：
    - 检索该品类的 [官方政策] (Policy)：平台硬性规则，如退换货政策、保修条款。
    - 检索该品类的 [风控规则] (Risk Control)：黑名单、高风险特征、已知质量缺陷。
    - 自动过滤低优先级的 FAQ，确保 Critic 拿到的是"铁律"级别的规则。
    
    使用场景：
    - 用户对正品存疑时 → risk_type="authenticity"
    - 关注退换货政策时 → risk_type="after_sales"
    - 怀疑价格虚高时 → risk_type="price_fraud"
    - 担心质量问题时 → risk_type="quality"
    """
    logger.info(f"[Critic Knowledge] 检索风控规则: {product_name} ({category}), 风险类型: {risk_type}")
    
    # 构造查询词：结合商品名、品类和风险类型，提高检索精准度
    query = f"{product_name} {category}"
    if risk_type:
        # 将英文风险类型映射为中文查询词
        risk_type_map = {
            "authenticity": "正品 真假 翻新",
            "after_sales": "售后 退换货 保修",
            "price_fraud": "价格 虚高 欺诈",
            "quality": "质量 缺陷 投诉"
        }
        query += f" {risk_type_map.get(risk_type, risk_type)}"
    
    # 调用底层知识管理器，指定只检索高优先级的来源类型
    # 聚焦铁律：policy (官方政策) 和 risk_control (风控规则)
    result = await knowledge_manager.query_knowledge(
        query=query,
        category=category,
        source_types=["policy", "risk_control"],  # 只查铁律
        top_k=3
    )
    
    if not result:
        return f"知识库中暂未找到关于 '{product_name}' 的明确风控规则，请基于通用逻辑评估风险。"
    
    logger.info(f"[Critic Knowledge] 检索到 {len(result)} 条相关规则")
    return result
