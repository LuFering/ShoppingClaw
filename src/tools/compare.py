from __future__ import annotations

from typing import List

from pydantic import BaseModel

from src.models.product import Product


class ComparisonResult(BaseModel):
    report: str
    ranked_products: List[Product]


def _safe_positive_float(value: object) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _safe_rating(value: object) -> float:
    try:
        rating = float(value)
    except (TypeError, ValueError):
        return 0.0
    if rating < 0:
        return 0.0
    if rating > 5:
        return 5.0
    return rating


def _safe_non_negative_int(value: object) -> int | None:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number >= 0 else None


def _format_price_display(value: object) -> str:
    price = _safe_positive_float(value)
    if price is None:
        return "未知"
    return f"{price:.2f}"


def compare_products(products: List[Product]) -> ComparisonResult:
    if not products:
        return ComparisonResult(report="没有商品可对比", ranked_products=[])

    if len(products) == 1:
        p = products[0]
        return ComparisonResult(
            report=f"单个商品对比（只有一个商品可对比）：{p.title}，价格¥{_format_price_display(p.price)}",
            ranked_products=products,
        )

    scored_products = []
    for product in products:
        score = _calculate_score(product, products)
        scored_products.append((score, product))

    scored_products.sort(key=lambda x: x[0], reverse=True)
    ranked_products = [p for _, p in scored_products]
    report = _generate_report(ranked_products)
    return ComparisonResult(report=report, ranked_products=ranked_products)


def _calculate_score(product: Product, all_products: List[Product]) -> float:
    current_price = _safe_positive_float(product.price)
    prices = [price for price in (_safe_positive_float(p.price) for p in all_products) if price is not None]
    if prices:
        min_price, max_price = min(prices), max(prices)
        if max_price > min_price and current_price is not None:
            price_score = (max_price - current_price) / (max_price - min_price)
            price_score = max(0.0, min(1.0, price_score))
        elif current_price is not None:
            price_score = 1.0
        else:
            price_score = 0.5
    else:
        price_score = 0.5

    rating_score = _safe_rating(product.rating) / 5.0

    current_sales = _safe_non_negative_int(product.sales_count)
    sales = [sales_count for sales_count in (_safe_non_negative_int(p.sales_count) for p in all_products) if sales_count is not None]
    if sales:
        min_sales, max_sales = min(sales), max(sales)
        if max_sales > min_sales and current_sales is not None:
            sales_score = (current_sales - min_sales) / (max_sales - min_sales)
            sales_score = max(0.0, min(1.0, sales_score))
        elif current_sales is not None:
            sales_score = 1.0
        else:
            sales_score = 0.5
    else:
        sales_score = 0.5

    return price_score * 0.4 + rating_score * 0.4 + sales_score * 0.2


def _generate_report(ranked_products: List[Product]) -> str:
    lines = ["商品对比报告（按综合得分排序）：", ""]
    for i, p in enumerate(ranked_products[:5], start=1):
        lines.append(
            f"{i}. {p.title} | 价格: ¥{_format_price_display(p.price)} | 评分: {p.rating or '未知'} | 销量: {p.sales_count or '未知'}"
        )
    return "\n".join(lines)
