from typing import List
from pydantic import BaseModel
from src.models.product import Product


class ComparisonResult(BaseModel):
    """对比结果"""
    report: str                    # 自然语言对比报告
    ranked_products: List[Product]  # 排序后的商品列表


def compare_products(
    products: List[Product],
) -> ComparisonResult:
    """
    商品对比工具
    
    职责：
    - 按维度分析每个商品
    - 计算综合得分
    - 生成自然语言对比报告
    - 返回排序后的商品列表
    
    对比维度：
    - 价格：越低越好（权重40%）
    - 评分：越高越好（权重40%）
    - 销量：越高越好（权重20%）
    
    参数：
        products: 商品列表
    
    返回：
        ComparisonResult: 包含报告和排序结果
    
    示例：
        >>> result = compare_products(products)
        >>> print(result.report)
        >>> result.ranked_products[0].title
        'iPhone 15 Pro'
    """
    if not products:
        return ComparisonResult(
            report="没有商品可对比",
            ranked_products=[]
        )
    
    if len(products) == 1:
        return ComparisonResult(
            report=f"单个商品对比：{products[0].title}，价格¥{products[0].price}",
            ranked_products=products
        )
    
    # 计算每个商品的得分
    scored_products = []
    for product in products:
        score = _calculate_score(product, products)
        scored_products.append((score, product))
    
    # 按得分排序（得分越高越好）
    scored_products.sort(key=lambda x: x[0], reverse=True)
    ranked_products = [p for _, p in scored_products]
    
    # 生成对比报告
    report = _generate_report(ranked_products)
    
    return ComparisonResult(
        report=report,
        ranked_products=ranked_products
    )


def _calculate_score(product: Product, all_products: List[Product]) -> float:
    """
    计算商品综合得分
    
    权重：
    - 价格：40%（越低越好）
    - 评分：40%（越高越好）
    - 销量：20%（越高越好）
    """
    # 价格得分（越低越好）
    # Optimize by Claude
    # price can not be None
    # prices = [p.price for p in all_products if p.price]
    prices = [p.price for p in all_products]
    
    if prices:
        min_price, max_price = min(prices), max(prices)
        if max_price > min_price:
            price_score = (max_price - product.price) / (max_price - min_price)
        else:
            price_score = 1.0
    else:
        price_score = 0.5
    
    # 评分得分（越高越好）
    rating_score = (product.rating or 0) / 5.0
    
    # 销量得分（越高越好）
    sales = [p.sales_count for p in all_products if p.sales_count]
    if sales:
        min_sales, max_sales = min(sales), max(sales)
        if max_sales > min_sales:
            # sales_score = (product.sales_count or 0) / max_sales
            sales_score = (
            (product.sales_count or 0) - min_sales
        ) / (max_sales - min_sales)
        # Optimize by Claude
        else:
            sales_score = 1.0
    else:
        sales_score = 0.5
    
    # 综合得分
    total_score = (
        price_score * 0.4 +
        rating_score * 0.4 +
        sales_score * 0.2
    )
    
    return total_score


def _generate_report(products: List[Product]) -> str:
    """生成自然语言对比报告"""
    report = f"商品对比报告（共{len(products)}个商品）：\n\n"
    
    for i, product in enumerate(products, 1):
        report += f"{i}. {product.title}\n"
        report += f"   平台：{product.platform}\n"
        report += f"   价格：¥{product.price}\n"
        if product.rating:
            report += f"   评分：{product.rating}⭐\n"
        if product.sales_count:
            report += f"   销量：{product.sales_count}\n"
        report += "\n"
    
    return report