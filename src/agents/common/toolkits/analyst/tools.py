import logging
from typing import List, Optional, Dict, Any

from src.agents.common.toolkits.registry import tool
from src.knowledge.manager import knowledge_manager
from .schemas import GetProductsSpecsInput, FilterProductsInput, QueryKnowledgeInput

logger = logging.getLogger(__name__)


@tool(
    category="analyst",
    tags=["规格", "对比", "参数"],
    display_name="批量获取商品规格",
    icon="📋",
    args_schema=GetProductsSpecsInput,
)
def get_products_specs_extract(products: List[dict]) -> List[Dict[str, Any]]:
    """
    从商品对象中提取并标准化关键规格参数，为 Analyst 提供对比矩阵数据。
    
    职责：
    - 将商品字典转化为易于 LLM 理解的标准化格式
    - 提取核心决策因子（价格、评分、销量、品牌、标题）
    - 如果商品中有扩展的 specs 字段，一并返回
    """
    logger.info(f"[Analyst Tool] 提取 {len(products)} 个商品的规格参数")
    
    if not products:
        return []
        
    specs_list = []
    for p in products:
        # 基础决策因子
        spec = {
            "id": p.get("id"),
            "title": p.get("title"),
            "price": p.get("price"),
            "rating": p.get("rating", 0) or 0,
            "sales_count": p.get("sales_count", 0) or 0,
            "brand": p.get("brand", "未知"),
            "platform": p.get("platform"),
        }
        
        # 如果产品对象中包含更详细的 specs 字典，合并进去
        if "specs" in p and p["specs"]:
            spec["detailed_specs"] = p["specs"]
            
        specs_list.append(spec)
        
    return specs_list


@tool(
    category="analyst",
    tags=["过滤", "筛选", "红线"],
    display_name="基于硬性条件过滤商品",
    icon="🔍",
    args_schema=FilterProductsInput,
)
def filter_products_by_criteria(
    products: List[dict],
    max_price: Optional[float] = None,
    min_rating: Optional[float] = None,
    required_brands: Optional[List[str]] = None,
    exclude_keywords: Optional[List[str]] = None,
) -> List[dict]:
    """
    根据用户的硬性约束（红线）过滤商品列表。
    
    职责：
    - 剔除超出预算的商品
    - 剔除评分过低的商品
    - 剔除不符合品牌要求或包含排斥关键词的商品
    """
    logger.info(f"[Analyst Tool] 执行硬性过滤: max_price={max_price}, min_rating={min_rating}")
    
    filtered = products
    
    # 1. 价格过滤
    if max_price is not None:
        filtered = [p for p in filtered if p.get("price", 0) <= max_price]
        
    # 2. 评分过滤
    if min_rating is not None:
        filtered = [p for p in filtered if (p.get("rating", 0) or 0) >= min_rating]
        
    # 3. 品牌过滤
    if required_brands:
        filtered = [p for p in filtered if p.get("brand", "") in required_brands]
        
    # 4. 关键词排斥过滤
    if exclude_keywords:
        lower_keywords = [k.lower() for k in exclude_keywords]
        filtered = [
            p for p in filtered 
            if not any(kw in str(p.get("title", "")).lower() for kw in lower_keywords)
        ]
        
    logger.info(f"[Analyst Tool] 过滤结果: {len(filtered)} / {len(products)}")
    return filtered


@tool(
    category="analyst",
    tags=["知识库", "选购标准", "行业经验"],
    display_name="检索品类决策知识",
    icon="🧠",
    args_schema=QueryKnowledgeInput,
)
async def query_category_knowledge(
    category: str,
    focus_area: Optional[str] = None,
) -> str:
    """
    为 Analyst 提供特定品类的专业决策标准和历史经验。
    
    职责：
    - 检索该品类的 [决策标准] (Framework)：官方或行业公认的选购维度。
    - 检索该品类的 [经验结论] (Experience)：基于真实用户反馈的避坑指南。
    - 自动过滤低优先级的 FAQ，确保 Analyst 拿到的是“专家级”建议。
    """
    logger.info(f"[Analyst Knowledge] 检索品类: {category}, 关注点: {focus_area}")
    
    # 构造查询词：结合品类和关注点，提高检索精准度
    query = f"{category} 选购标准"
    if focus_area:
        query += f" {focus_area}"
        
    # 调用底层知识管理器，指定只检索高价值的来源类型
    # 聚焦专家知识：framework (决策标准) 和 experience (经验结论)
    result = await knowledge_manager.query_knowledge(
        query=query,
        category=category,
        source_types=["framework", "experience"],
        top_k=3
    )
    
    if not result:
        return f"知识库中暂未找到关于 '{category}' 的深度决策标准，请基于通用逻辑进行分析。"
        
    return result
