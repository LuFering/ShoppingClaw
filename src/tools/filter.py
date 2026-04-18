from typing import List, Optional
from src.models.product import Product, PlatformCode


def filter_products(
    products: List[Product],
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    platforms: Optional[List[PlatformCode]] = None,
    min_rating: Optional[float] = None,
    brands: Optional[List[str]] = None,
    keywords: Optional[List[str]] = None,
) -> List[Product]:
    """
    商品过滤工具
    
    职责：
    - 根据多个条件过滤商品列表
    - 返回符合条件的商品列表
    
    参数：
        products: 商品列表
        price_min: 最低价格
        price_max: 最高价格
        platforms: 指定平台列表（如["jd", "taobao"]）
        min_rating: 最低评分（0-5）
        brands: 指定品牌列表
        keywords: 标题包含的关键词列表（OR逻辑，大小写不敏感）
    
    返回：
        List[Product]: 符合条件的商品列表
    
    异常：
        ValueError: price_min > price_max
        ValueError: min_rating超出范围
    
    示例：
        >>> filtered = filter_products(products, price_min=1000, price_max=5000)
        >>> len(filtered)
        10
    """
    # 参数校验
    if price_min is not None and price_max is not None and price_min > price_max:
        raise ValueError("price_min不能大于price_max")
    
    if min_rating is not None and (min_rating < 0 or min_rating > 5):
        raise ValueError("min_rating必须在0-5之间")
    
    filtered = products
    # Claude said that it can be merged
    # 价格过滤
    # if price_min is not None:
    #     filtered = [p for p in filtered if p.price >= price_min]
    
    # if price_max is not None:
    #     filtered = [p for p in filtered if p.price <= price_max]
    if price_min is not None or price_max is not None:
        filtered = [
        p for p in filtered
        if (price_min is None or p.price >= price_min)
        and (price_max is None or p.price <= price_max)
    ]
    
    # 平台过滤
    if platforms is not None:
        filtered = [p for p in filtered if p.platform in platforms]
    
    # 评分过滤
    if min_rating is not None:
        # Claude it
        # filtered = [p for p in filtered if p.rating and p.rating >= min_rating]
        filtered = [p for p in filtered if p.rating is not None and p.rating >= min_rating]
    
    # 品牌过滤
    if brands is not None:
        # Claude it
        # filtered = [p for p in filtered if p.brand and p.brand in brands]
        filtered = [p for p in filtered if p.brand is not None and p.brand in brands]
    
    # 关键词过滤（OR逻辑，大小写不敏感）
    if keywords is not None:
        keywords_lower = [k.lower() for k in keywords]
        filtered = [
            p for p in filtered
            if any(keyword in p.title.lower() for keyword in keywords_lower)
        ]
    
    return filtered