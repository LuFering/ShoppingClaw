"""Research Agent 工具集 - 基于京东官方API + JustoneAPI

使用京东开放平台SDK + JustoneAPI实现商品搜索、详情查询等功能。
"""
import logging
import os
import json
import requests
from typing import Dict, Any, List, Optional
from urllib.parse import quote
from pydantic import BaseModel, Field

try:
    from src import jd  # type: ignore
except Exception:
    jd = None  # type: ignore[assignment]
from src.agents.common.toolkits.registry import tool
from src.agents.common.toolkits.research.schemas import (
    JdDeepSearchInput,
    JdProductDetailInput,
    JdShopReliabilityInput,
    JdProductImagesInput,
    JdProductBasicInput,
    JdProductMobileDetailInput,
    JustoneProductSearchInput,
    JustoneProductDetailInput,
    ProductFullDetailInput,
)
from src.models.product import Product

logger = logging.getLogger(__name__)

# JustoneAPI配置
JUSTONE_API_KEY = os.getenv("JUSTONE_API_KEY")
JUSTONE_BASE_URL = os.getenv("JUSTONE_BASE_URL", "https://api.justoneapi.com")


def _parse_sales(sales_str: Optional[str]) -> Optional[int]:
    """解析销量字符串为整数（如'超1万人已购买' → 10000）"""
    if not sales_str:
        return None
    
    import re
    # 提取数字
    match = re.search(r'(\d+)', sales_str)
    if match:
        num = int(match.group(1))
        # 判断单位
        if '万' in sales_str:
            return num * 10000
        elif '千' in sales_str:
            return num * 1000
        else:
            return num
    return None


def _safe_price(value: Any) -> float:
    try:
        price = float(value)
    except Exception:
        return 1.0
    return price if price > 0 else 1.0


def _safe_url(url: Any, *, fallback: str) -> str:
    s = str(url or "").strip()
    if s.lower().startswith("http"):
        return s
    return fallback


def _safe_image_url(url: Any) -> str | None:
    s = str(url or "").strip()
    if s.lower().startswith("http"):
        return s
    return None


def _build_seed_product(sku_id: str, existing_product: Product | None = None) -> Product:
    if existing_product is not None:
        return existing_product
    return Product(
        id=f"jd_{sku_id}",
        title=f"JD商品{sku_id}",
        price=1.0,
        state=1,
        platform="jd",
        url=f"https://item.jd.com/{sku_id}.html",
    )


def _merge_dict_value(base: dict | None, extra: dict | None) -> dict | None:
    merged = dict(base or {})
    for key, value in (extra or {}).items():
        if value in (None, "", [], {}):
            continue
        merged[key] = value
    return merged or None


def _enrich_product(
    sku_id: str,
    existing_product: Product | None = None,
    *,
    title: Any = None,
    price: Any = None,
    url: Any = None,
    image_url: Any = None,
    state: Any = None,
    shop_name: Any = None,
    brand: Any = None,
    category: Any = None,
    rating: Any = None,
    sales_count: Any = None,
    specs: dict | None = None,
    after_sales_info: dict | None = None,
    delivery_info: dict | None = None,
    increment_service: dict | None = None,
    promo_info: dict | None = None,
    rank_info: dict | None = None,
    good_comment_keywords: list | None = None,
    installment_info: Any = None,
    promo_tags: Any = None,
) -> Product:
    base = _build_seed_product(sku_id, existing_product)
    updates: dict[str, Any] = {}

    title_str = str(title or "").strip()
    if title_str and (not base.title or base.title.startswith("JD商品")):
        updates["title"] = title_str

    price_num = _safe_price(price) if price is not None else None
    if price_num is not None and (base.price <= 1.0 or price_num != base.price):
        updates["price"] = price_num

    if state is not None:
        try:
            updates["state"] = int(state)
        except Exception:
            pass

    safe_url = _safe_url(url, fallback=str(base.url))
    if safe_url != str(base.url):
        updates["url"] = safe_url

    safe_img = _safe_image_url(image_url)
    if safe_img:
        updates["image_url"] = safe_img

    for field_name, value in {
        "shop_name": shop_name,
        "brand": brand,
        "category": category,
        "installment_info": installment_info,
        "promo_tags": promo_tags,
    }.items():
        value_str = str(value or "").strip()
        if value_str:
            updates[field_name] = value_str

    if rating is not None:
        try:
            rating_val = float(rating)
            if 0 <= rating_val <= 5:
                updates["rating"] = rating_val
        except Exception:
            pass

    if sales_count is not None:
        try:
            updates["sales_count"] = int(sales_count)
        except Exception:
            pass

    merged_specs = _merge_dict_value(base.specs, specs)
    if merged_specs is not None:
        updates["specs"] = merged_specs
        updates["key_specs"] = merged_specs

    for field_name, extra in {
        "after_sales_info": after_sales_info,
        "delivery_info": delivery_info,
        "increment_service": increment_service,
        "promo_info": promo_info,
        "rank_info": rank_info,
    }.items():
        merged = _merge_dict_value(getattr(base, field_name), extra)
        if merged is not None:
            updates[field_name] = merged

    if good_comment_keywords:
        current = list(base.good_comment_keywords or [])
        for item in good_comment_keywords:
            if item not in current:
                current.append(item)
        if current:
            updates["good_comment_keywords"] = current

    return base.model_copy(update=updates)


def init_jd_sdk():
    """初始化京东SDK认证"""
    if jd is None:
        logger.warning("[JD API] 京东SDK不可用")
        return False, None
    # 从环境变量读取配置
    app_key = os.getenv("JD_APP_KEY")
    app_secret = os.getenv("JD_APP_SECRET")
    access_token = os.getenv("JD_ACCESS_TOKEN")
    
    if not app_key or not app_secret:
        logger.warning("[JD API] 未配置JD_APP_KEY或JD_APP_SECRET")
        return False, None
    
    jd.setDefaultAppInfo(app_key, app_secret)
    logger.info(f"[JD API] SDK初始化完成 | Access Token: {'已配置' if access_token else '未配置'}")
    return True, access_token


# ==================== 工具1: jd_deep_search - 深度商品搜索 ====================

@tool(
    category="research",
    tags=["搜索", "官方API", "商品"],
    display_name="京东商品搜索（官方API）",
    icon="🔍",
    args_schema=JdDeepSearchInput,
)
def jd_deep_search(
    keyword: str,
    max_pages: int = 3,
    max_empty_pages: int = 3,
    include_details: bool = False,
) -> Dict[str, Any]:
    """
    使用京东官方API搜索商品。
    
    Args:
        keyword: 搜索关键词
        max_pages: 最多爬取的页数（1-10）
        max_empty_pages: 未使用（API分页控制）
        include_details: 是否包含详细信息
    
    Returns:
        包含商品列表、统计信息和错误状态的字典
    """
    logger.info(f"[Tool] 京东API搜索: {keyword} | 最大页数: {max_pages}")
    
    try:
        success, access_token = init_jd_sdk()
        if not success:
            return {"products": [], "error": "京东官方API未配置或不可用"}
        
        from src.jd.api.rest.SearchWareRequest import SearchWareRequest
        
        products: list[Product] = []
        
        for page in range(1, max_pages + 1):
            # 创建搜索请求
            request = SearchWareRequest('https://api.jd.com/routerjson', 80)
            # URL编码关键词
            from urllib.parse import quote
            request.key = quote(keyword)
            request.page = str(page)
            
            # 调用API
            response = request.getResponse(access_token=access_token)
            
            # 解析返回数据
            if response and 'jingdong_search_ware_responce' in response:
                res = response['jingdong_search_ware_responce']
                paragraph = res.get('Paragraph', [])
                
                from urllib.parse import unquote

                for item in paragraph:
                    content = item.get("Content", {})
                    sku = str(item.get("wareid") or "").strip()
                    title = str(unquote(content.get("warename") or "")).strip()
                    if not sku or not title:
                        continue
                    raw_img = str(content.get("imageurl") or "").strip()
                    if raw_img.lower().startswith("http"):
                        image_url = raw_img
                    elif raw_img:
                        image_url = f"https://img10.360buyimg.com/n1/{raw_img}"
                    else:
                        image_url = None

                    products.append(
                        Product(
                            id=f"jd_{sku}",
                            title=title,
                            price=1.0,
                            state=1,
                            platform="jd",
                            url=f"https://item.jd.com/{sku}.html",
                            image_url=_safe_image_url(image_url),
                        )
                    )

            logger.info(f"[Tool] 第{page}页累计 {len(products)} 个商品")

        return {"products": products, "error": None}
    
    except Exception as e:
        logger.error(f"[Tool] 京东API搜索失败: {e}")
        return {"products": [], "error": str(e)}


# ==================== 工具2: jd_product_detail - 商品详情 ====================

@tool(
    category="research",
    tags=["详情", "官方API", "SKU", "规格参数"],
    display_name="京东商品详情（官方API）",
    icon="📋",
    args_schema=JdProductDetailInput,
)
def jd_product_detail(
    sku_id: str,
    existing_product: Product | None = None,
    fetch_specs: bool = True,
    fetch_description: bool = False,
) -> Dict[str, Any]:
    """
    使用京东官方API获取商品详情（规格、参数、描述）。
    
    Args:
        sku_id: 商品SKU ID
        fetch_specs: 是否获取规格参数
        fetch_description: 是否获取图文详情
    
    Returns:
        包含商品详细信息和错误状态的字典
    """
    logger.info(f"[Tool] 京东API商品详情: {sku_id}")
    
    try:
        success, access_token = init_jd_sdk()
        if not success:
            return {"products": [], "error": "京东官方API未配置或不可用"}
        
        from src.jd.api.rest.WareProductbigfieldGetRequest import WareProductbigfieldGetRequest
        
        request = WareProductbigfieldGetRequest('https://api.jd.com/routerjson', 80)
        request.sku_id = sku_id
        
        # field参数：传入要查询的字段（根据京东API文档）
        # 支持：wareQD(包装清单)、propCode(规格参数)、wdis(商品介绍)、shouhou(售后)等
        if fetch_specs and fetch_description:
            request.field = "wareQD,propCode,wdis"  # 规格参数+商品介绍
        elif fetch_specs:
            request.field = "wareQD,propCode"  # 仅规格参数
        else:
            request.field = "wdis"  # 仅商品介绍
        
        response = request.getResponse()  # 无需access_token
        
        # 解析返回数据
        if response and "jingdong_ware_productbigfield_get_responce" in response:
            res = response["jingdong_ware_productbigfield_get_responce"]

            specs: dict[str, str] = {}
            ware_qd = res.get("wareQD")
            prop_code = res.get("propCode")
            wdis = res.get("wdis")
            if ware_qd:
                specs["wareQD"] = str(ware_qd)
            if prop_code:
                specs["propCode"] = str(prop_code)
            if wdis:
                specs["wdis"] = str(wdis)

            p = _enrich_product(
                sku_id,
                existing_product,
                specs=specs,
            )
            return {"products": [p], "error": None}

        return {"products": [], "error": "京东官方API返回数据格式异常"}
    
    except Exception as e:
        logger.error(f"[Tool] 京东API商品详情失败: {e}")
        return {"products": [], "error": str(e)}


# ==================== 工具3: jd_shop_reliability - 店铺可靠性 ====================

@tool(
    category="research",
    tags=["店铺", "官方API", "可靠性"],
    display_name="京东店铺评估（官方API）",
    icon="🏪",
    args_schema=JdShopReliabilityInput,
)
def jd_shop_reliability(
    shop_name: str,
    shop_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    使用京东官方API评估店铺可靠性。
    
    Args:
        shop_name: 店铺名称
        shop_id: 店铺ID
    
    Returns:
        包含店铺可靠性评估和错误状态的字典
    """
    logger.info(f"[Tool] 京东API店铺评估: {shop_name}")

    _ = shop_id
    return {"products": [], "error": "京东店铺评估暂未实现"}


# ==================== 工具5: jd_product_images - 商品图片 ====================

@tool(
    category="research",
    tags=["图片", "官方API", "SKU", "批量查询"],
    display_name="京东商品图片查询（官方API）",
    icon="🖼️",
    args_schema=JdProductImagesInput,
)
def jd_product_images(
    sku_ids: List[str],
) -> Dict[str, Any]:
    """
    使用京东官方API批量查询商品图片。
    
    Args:
        sku_ids: 商品SKU ID列表（支持批量查询，最多100个）
    
    Returns:
        包含商品图片列表和错误状态的字典
    """
    logger.info(f"[Tool] 京东API商品图片查询: {len(sku_ids)} 个SKU")
    
    try:
        success, access_token = init_jd_sdk()
        if not success:
            return {"products": [], "error": "京东官方API未配置或不可用"}
        
        from src.jd.api.rest.WareProductimageGetRequest import WareProductimageGetRequest
        
        request = WareProductimageGetRequest('https://api.jd.com/routerjson', 80)
        # 将字符串列表转为整数列表
        request.sku_id = [int(sku_id) for sku_id in sku_ids]
        
        response = request.getResponse()  # 无需access_token
        
        # 解析返回数据
        if response and 'jingdong_ware_productimage_get_responce' in response:
            res = response['jingdong_ware_productimage_get_responce']
            image_path_list = res.get('image_path_list', [])
            
            results: dict[str, dict[str, Any]] = {}
            for item in image_path_list:
                sku_id_str = str(item.get('sku_id', ''))
                images = item.get('image_list', [])
                
                # 提取图片信息
                image_info = []
                for img in images:
                    image_info.append({
                        "url": img.get('path', ''),
                        "is_primary": img.get('is_primary') == 1,
                        "order": img.get('orderSort', 0),
                        "image_id": img.get('id', 0),
                    })
                
                results[sku_id_str] = {
                    "total_images": len(image_info),
                    "primary_image": next((img["url"] for img in image_info if img["is_primary"]), None),
                    "images": image_info,
                }

            products: list[Product] = []
            for sku in sku_ids:
                primary = (results.get(str(sku)) or {}).get("primary_image")
                p = Product(
                    id=f"jd_{sku}",
                    title=f"JD商品{sku}",
                    price=1.0,
                    state=1,
                    platform="jd",
                    url=f"https://item.jd.com/{sku}.html",
                    image_url=_safe_image_url(primary),
                )
                products.append(p)

            return {"products": products, "error": None}

        return {"products": [], "error": "京东官方API返回数据格式异常"}
    
    except Exception as e:
        logger.error(f"[Tool] 京东API商品图片查询失败: {e}")
        return {"products": [], "error": str(e)}


# ==================== 工具6: jd_product_basic - 商品基础信息 ====================

@tool(
    category="research",
    tags=["基础信息", "官方API", "SKU", "批量查询", "快速预览"],
    display_name="京东商品基础信息（官方API）",
    icon="📦",
    args_schema=JdProductBasicInput,
)
def jd_product_basic(
    sku_ids: List[str],
    fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    使用京东官方API批量查询商品基础信息（轻量级快速预览）。
    
    Args:
        sku_ids: 商品SKU ID列表（支持批量查询）
        fields: 需要返回的字段列表，如['name', 'isDelete']。默认返回['name', 'isDelete']。
                API会自动附加skuId和url字段。
    
    Returns:
        包含商品基础信息和错误状态的字典
    """
    logger.info(f"[Tool] 京东API商品基础信息查询: {len(sku_ids)} 个SKU")
    
    try:
        success, access_token = init_jd_sdk()
        if not success:
            return {"products": [], "error": "京东官方API未配置或不可用"}
        
        from src.jd.api.rest.NewWareBaseproductGetRequest import NewWareBaseproductGetRequest
        
        request = NewWareBaseproductGetRequest('https://api.jd.com/routerjson', 80)
        # 将字符串列表转为整数列表（官方API要求ids=Number[]类型）
        request.ids = [int(sku_id) for sku_id in sku_ids]
        
        # 设置返回字段（默认返回name和isDelete）
        if fields:
            request.basefields = ",".join(fields)
        else:
            request.basefields = "name,isDelete"  # 必须包含至少一个有效字段
        
        response = request.getResponse()  # 无需access_token
        
        # 解析返回数据
        if response and 'jingdong_new_ware_baseproduct_get_responce' in response:
            res = response['jingdong_new_ware_baseproduct_get_responce']
            product_list = res.get('listproductbase_result', [])
            
            results: dict[str, dict[str, Any]] = {}
            for product in product_list:
                sku_id_str = str(product.get('skuId', ''))
                results[sku_id_str] = {
                    "name": product.get('name', ''),  # 注意：字段名是name不是pname
                    "is_delete": product.get('isDelete', ''),  # 1=上架, 0=下架
                    "url": product.get('url', ''),
                }

            products: list[Product] = []
            for sku in sku_ids:
                r = results.get(str(sku)) or {}
                name = str(r.get("name") or "").strip() or f"JD商品{sku}"
                is_delete = r.get("is_delete")
                try:
                    state = 1 if int(is_delete) == 1 else 0
                except Exception:
                    state = 1
                url_val = _safe_url(r.get("url"), fallback=f"https://item.jd.com/{sku}.html")
                products.append(
                    Product(
                        id=f"jd_{sku}",
                        title=name,
                        price=1.0,
                        state=state,
                        platform="jd",
                        url=url_val,
                    )
                )

            return {"products": products, "error": None}

        return {"products": [], "error": "京东官方API返回数据格式异常"}
    
    except Exception as e:
        logger.error(f"[Tool] 京东API商品基础信息查询失败: {e}")
        return {"products": [], "error": str(e)}


# ==================== 工具7: jd_product_mobile_detail - 移动端详情 ====================

@tool(
    category="research",
    tags=["移动端详情", "官方API", "SKU", "富文本"],
    display_name="京东移动端商品详情（官方API）",
    icon="",
    args_schema=JdProductMobileDetailInput,
)
def jd_product_mobile_detail(
    sku_id: str,
    existing_product: Product | None = None,
    fields: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    使用京东官方API获取移动端商品详情（HTML富文本格式）。
    
    Args:
        sku_id: 商品SKU ID
        fields: 需要查询的字段列表，如['wareQD', 'propCode', 'wdis']
    
    Returns:
        包含移动端商品详情HTML和错误状态的字典
    """
    logger.info(f"[Tool] 京东API移动端商品详情: {sku_id}")
    
    try:
        success, access_token = init_jd_sdk()
        if not success:
            return {"products": [], "error": "京东官方API未配置或不可用"}
        
        from src.jd.api.rest.NewWareMobilebigfieldGetRequest import NewWareMobilebigfieldGetRequest
        
        request = NewWareMobilebigfieldGetRequest('https://api.jd.com/routerjson', 80)
        request.skuid = int(sku_id)  # 注意：参数名是skuid，类型是Number
        
        # 设置查询字段（默认查询全部）
        if fields:
            request.field = ",".join(fields)
        else:
            request.field = "wareQD,propCode,wdis"
        
        response = request.getResponse()  # 无需access_token
        
        # 解析返回数据
        if response and 'jingdong_new_ware_mobilebigfield_get_responce' in response:
            res = response['jingdong_new_ware_mobilebigfield_get_responce']
            html_content = res.get('result', '')

            p = _enrich_product(
                sku_id,
                existing_product,
                specs={"mobile_html": str(html_content or "")},
            )
            return {"products": [p], "error": None}

        return {"products": [], "error": "京东官方API返回数据格式异常"}
    
    except Exception as e:
        logger.error(f"[Tool] 京东API移动端商品详情失败: {e}")
        return {"products": [], "error": str(e)}


# ==================== 工具8: search_products - 整合搜索（官方+Justone） ====================

@tool(
    category="research",
    tags=["搜索", "整合", "价格", "销量"],
    display_name="商品搜索（官方+Justone整合）",
    icon="🔍",
)
def search_products(
    keyword: str,
    page: int = 1,
    need_price: bool = True
) -> Dict[str, Any]:
    """
    搜索商品，**自动整合两个数据源的优势**。
    
    数据源特点：
    - 官方API: 好评率、店铺ID、类目（无价格）
    - JustoneAPI: 价格、销量、好评关键词、店铺名称、服务保障
    
    参数：
    - keyword: 搜索关键词
    - page: 页码（默认1）
    - need_price: 是否需要价格（默认True，会自动调用Justone）
    
    返回：
    **已映射到Product模型的结构化数据**，包含：
    - id, title, price, platform, url, image_url
    - shop_name, sales_count, good_comment_keywords
    - installment_info, promo_tags
    - good_rate（额外字段，非Product标准）
    """
    logger.info(f"[Tool] 整合搜索: {keyword} | 页码: {page}")
    
    products: list[Product] = []
    errors: list[str] = []
    
    # 1. 优先用官方API获取基础数据（可选依赖：jd SDK）
    try:
        success, access_token = init_jd_sdk()
        if success:
            from src.jd.api.rest.SearchWareRequest import SearchWareRequest
            
            request = SearchWareRequest('https://api.jd.com/routerjson', 80)
            request.key = quote(keyword)
            request.page = str(page)
            
            response = request.getResponse(access_token=access_token)
            
            if response and 'jingdong_search_ware_responce' in response:
                res = response['jingdong_search_ware_responce']
                paragraph = res.get('Paragraph', [])
                
                for item in paragraph:
                    content = item.get('Content', {})
                    sku = str(item.get("wareid", "")).strip()
                    title = str(content.get("warename", "")).strip()
                    if not sku or not title:
                        continue
                    image_path = str(content.get("imageurl", "")).strip()
                    image_url = f"https://img10.360buyimg.com/n1/{image_path}" if image_path else None
                    products.append(
                        Product(
                            id=f"jd_{sku}",
                            title=title,
                            price=1.0,
                            state=1,
                            platform="jd",
                            url=f"https://item.jd.com/{sku}.html",
                            image_url=image_url,
                        )
                    )
            else:
                errors.append("京东官方API返回为空")
        else:
            errors.append("京东官方API未配置或不可用")
    except Exception as e:
        logger.warning(f"[Tool] 官方API搜索失败: {e}")
        errors.append(f"京东官方API异常: {e}")
    
    # 2. 用 JustoneAPI 补齐价格/销量/店铺等（如果官方API不可用，这一步也可以单独产出候选集）
    if need_price and JUSTONE_API_KEY:
        try:
            url = f"{JUSTONE_BASE_URL}/api/jd/search-item-list/v1"
            params = {
                "token": JUSTONE_API_KEY,
                "keyword": keyword,
                "page": str(page)
            }
            
            response = requests.get(url, params=params, timeout=10)
            result = response.json()
            
            if result.get("code") == 0:
                justone_products = result.get("data", {}).get("products", [])
                if justone_products is None:
                    justone_products = []

                justone_map = {str(p.get("id")): p for p in justone_products if isinstance(p, dict) and p.get("id")}

                if products:
                    for idx, p in enumerate(list(products)):
                        sku_id = p.id.replace("jd_", "")
                        j = justone_map.get(sku_id)
                        if not j:
                            continue
                        try:
                            price = float(j.get("price")) if j.get("price") else 1.0
                        except Exception:
                            price = 1.0
                        products[idx] = p.model_copy(
                            update={
                                "price": price if price > 0 else 1.0,
                                "shop_name": j.get("shopName"),
                                "sales_count": _parse_sales(j.get("sales")),
                                "good_comment_keywords": j.get("gcw", []),
                                "installment_info": j.get("foi"),
                                "promo_tags": j.get("promoTag"),
                                "url": j.get("landUrl") or p.url,
                            }
                        )
                else:
                    for j in justone_products:
                        sku = str(j.get("id", "")).strip()
                        title = str(j.get("title", "") or j.get("name", "")).strip()
                        if not sku or not title:
                            continue
                        try:
                            price = float(j.get("price")) if j.get("price") else 1.0
                        except Exception:
                            price = 1.0
                        url_val = j.get("landUrl") or f"https://item.jd.com/{sku}.html"
                        image_url = j.get("imgUrl") or j.get("image") or None
                        products.append(
                            Product(
                                id=f"jd_{sku}",
                                title=title,
                                price=price if price > 0 else 1.0,
                                state=1,
                                platform="jd",
                                url=url_val,
                                image_url=image_url,
                                shop_name=j.get("shopName"),
                                sales_count=_parse_sales(j.get("sales")),
                                good_comment_keywords=j.get("gcw", []),
                                installment_info=j.get("foi"),
                                promo_tags=j.get("promoTag"),
                            )
                        )
            else:
                errors.append("JustoneAPI返回失败")
                        
        except Exception as e:
            logger.warning(f"[Tool] JustoneAPI搜索失败: {e}")
            errors.append(f"JustoneAPI异常: {e}")
    elif need_price and not JUSTONE_API_KEY:
        errors.append("JustoneAPI未配置")
    
    if not products and errors:
        return {"products": [], "error": "; ".join(errors)}
    return {"products": products, "error": None}


# ==================== 工具9: get_product_full_detail - 完整详情（官方+Justone） ====================

@tool(
    category="research",
    tags=["详情", "整合", "服务保障", "促销信息", "排行榜"],
    display_name="商品完整详情（官方+Justone整合）",
    icon="📊",
)
def get_product_full_detail(
    sku_id: str,
    existing_product: Product | None = None,
) -> Dict[str, Any]:
    """
    获取商品完整详情，**整合官方所有可用API + Justone详情API**。
    
    包含数据：
    - 基础信息: 品牌、型号、规格参数（官方baseproduct API）
    - 图片列表: 主图、详情图（官方productimage API）
    - 价格: Justone价格API
    - 服务保障: 7天无理由退货、价保、送货服务、售后政策（Justone详情API的stock.ir）
    - 促销信息: 赠品、满减、优惠券（Justone详情API的promov2）
    - 排行榜信息: 品类排名（Justone详情API的rankInfo）
    
    参数：
    - sku_id: 商品SKU ID
    
    返回：
    **已映射到Product模型的结构化数据**，包含：
    - id (jd_{sku_id}), title, price, platform, url, image_url
    - shop_name, brand, category
    - after_sales_info, delivery_info, increment_service
    - promo_info, rank_info, key_specs
    """
    logger.info(f"[Tool] 获取商品完整详情: {sku_id}")
    errors: list[str] = []
    # 初始化Product兼容结构
    detail: dict[str, Any] = {
        "title": None,
        "price": None,
        "url": None,
        "image_url": None,
        "shop_name": None,
        "brand": None,
        "category": None,
        "specs": {},
        "after_sales_info": {},
        "delivery_info": {},
        "increment_service": {},
        "promo_info": {},
        "rank_info": {},
    }
    
    # 1. 基础信息 + 规格参数（官方API）
    try:
        success, access_token = init_jd_sdk()
        if success:
            from src.jd.api.rest.NewWareBaseproductGetRequest import NewWareBaseproductGetRequest
            
            request = NewWareBaseproductGetRequest('https://api.jd.com/routerjson', 80)
            request.ids = [int(sku_id)]
            request.basefields = "wareInfo,basicInfo,specInfo,packInfo"
            
            response = request.getResponse(access_token=access_token)
            
            if response and 'jingdong_new_ware_baseproduct_get_responce' in response:
                res = response['jingdong_new_ware_baseproduct_get_responce']
                product_list = res.get('listproductbase_result', [])
                
                if product_list:
                    product = product_list[0]
                    detail['title'] = product.get('wareName')
                    detail['brand'] = product.get('brandName')
                    detail['category'] = product.get('categoryName')
                    # 提取关键规格
                    spec_info = product.get('specInfo', {})
                    if isinstance(spec_info, dict):
                        detail['specs'] = {
                            k: v for k, v in spec_info.items() 
                            if isinstance(v, str) and len(v) < 100  # 过滤长文本
                        }
        else:
            errors.append("京东官方API未配置或不可用")
    except Exception as e:
        logger.warning(f"[Tool] 官方API基础信息失败: {e}")
        errors.append(f"京东官方API基础信息异常: {e}")
    
    # 2. 商品图片（官方API）
    try:
        success, access_token = init_jd_sdk()
        if success:
            from src.jd.api.rest.WareProductimageGetRequest import WareProductimageGetRequest
            
            request = WareProductimageGetRequest('https://api.jd.com/routerjson', 80)
            request.skuId = int(sku_id)
            
            response = request.getResponse(access_token=access_token)
            
            if response and 'jingdong_ware_productimage_get_responce' in response:
                res = response['jingdong_ware_productimage_get_responce']
                images = res.get('imageList', [])
                if images:
                    detail['image_url'] = images[0].get('url')  # 主图
        else:
            errors.append("京东官方API未配置或不可用")
    except Exception as e:
        logger.warning(f"[Tool] 官方API图片失败: {e}")
        errors.append(f"京东官方API图片异常: {e}")
    
    # 3. 价格（JustoneAPI）
    if JUSTONE_API_KEY:
        try:
            url = f"{JUSTONE_BASE_URL}/api/jd/get-item-price/v1"
            params = {
                "token": JUSTONE_API_KEY,
                "itemId": sku_id
            }
            
            response = requests.get(url, params=params, timeout=10)
            result = response.json()
            
            if result.get('code') == 0:
                price_data = result.get('data', {}).get('data', [])
                if price_data:
                    detail['price'] = price_data[0].get('price')
        except Exception as e:
            logger.warning(f"[Tool] JustoneAPI价格失败: {e}")
            errors.append(f"JustoneAPI价格异常: {e}")
    else:
        errors.append("JustoneAPI未配置")
    
    # 4. 服务保障 + 促销信息（Justone详情API）
    if JUSTONE_API_KEY:
        try:
            url = f"{JUSTONE_BASE_URL}/api/jd/get-item-detail/v1"
            params = {
                "token": JUSTONE_API_KEY,
                "itemId": sku_id
            }
            
            response = requests.get(url, params=params, timeout=10)
            result = response.json()
            
            if result.get('code') == 0:
                data = result.get('data', {})
                
                # 4.1 服务保障信息（stock.ir）
                stock = data.get('stock', {})
                service_icons = stock.get('ir', [])
                
                after_sales = []
                delivery = []
                increment = []
                
                for icon in service_icons:
                    service_item = {
                        "name": icon.get('showName'),
                        "tip": icon.get('iconTip'),
                        "icon_code": icon.get('iconCode')
                    }
                    
                    icon_code = icon.get('iconCode', '')
                    if 'tuihuo' in icon_code or 'price' in icon_code:
                        after_sales.append(service_item)
                    elif 'sendpay' in icon_code or 'delivery' in icon_code:
                        delivery.append(service_item)
                    elif 'service_' in icon_code:
                        increment.append(service_item)
                
                detail['after_sales_info'] = {
                    "services": after_sales,
                    "is_self_operated": stock.get('D', {}).get('type') == 0
                }
                
                detail['delivery_info'] = {
                    "services": delivery,
                    "promise": stock.get('promiseResult'),
                    "freight_info": stock.get('dcashDesc')
                }
                
                detail['increment_service'] = {
                    "services": increment,
                    "product_area": data.get('product', {}).get('productArea'),
                    "warranty": data.get('product', {}).get('wserve')
                }
                
                # 4.2 促销信息（promov2）
                promo_list = data.get('promov2', [])
                if promo_list:
                    promo_info = []
                    for promo in promo_list:
                        pis = promo.get('pis', [])
                        for pi in pis:
                            promo_info.append({
                                "type": pi.get('promoType'),
                                "description": pi.get('10') or pi.get('18'),
                                "start_time": pi.get('st'),
                                "end_time": pi.get('d')
                            })
                    detail['promo_info'] = {
                        "promotions": promo_info,
                        "has_gift": len(promo_info) > 0
                    }
                
                # 4.3 排行榜信息（rankInfo）
                rank_list = data.get('rankInfo', [])
                if rank_list:
                    detail['rank_info'] = {
                        "rankings": [{
                            "name": r.get('name'),
                            "rank_num": r.get('rankNum'),
                            "title": r.get('title')
                        } for r in rank_list]
                    }
                
                # 补充店铺名称和URL
                detail['shop_name'] = stock.get('D', {}).get('shopName')
                detail['url'] = f"https://item.jd.com/{sku_id}.html"
                
        except Exception as e:
            logger.warning(f"[Tool] JustoneAPI详情失败: {e}")
            errors.append(f"JustoneAPI详情异常: {e}")
    
    has_data = any(
        [
            detail.get("title"),
            detail.get("price"),
            detail.get("image_url"),
            detail.get("shop_name"),
            detail.get("brand"),
            detail.get("category"),
            bool(detail.get("specs")),
            bool(detail.get("after_sales_info")),
            bool(detail.get("promo_info")),
            bool(detail.get("rank_info")),
        ]
    )
    if not has_data:
        return {"products": [], "error": "; ".join(errors) if errors else "详情获取失败"}

    p = _enrich_product(
        sku_id,
        existing_product,
        title=detail.get("title"),
        price=detail.get("price"),
        url=detail.get("url"),
        image_url=detail.get("image_url"),
        shop_name=detail.get("shop_name"),
        brand=detail.get("brand"),
        category=detail.get("category"),
        specs=detail.get("specs") or {},
        after_sales_info=detail.get("after_sales_info") or None,
        delivery_info=detail.get("delivery_info") or None,
        increment_service=detail.get("increment_service") or None,
        promo_info=detail.get("promo_info") or None,
        rank_info=detail.get("rank_info") or None,
    )

    return {"products": [p], "error": None}


# ==================== 工具10: get_products_specs - 批量规格对比 ====================

@tool(
    category="research",
    tags=["规格", "批量", "对比"],
    display_name="批量获取商品规格（用于对比）",
    icon="📋",
)
def get_products_specs_batch(sku_ids: List[str]) -> Dict[str, Any]:
    """
    批量获取多个商品的规格参数，用于对比分析。
    
    参数：
    - sku_ids: 商品SKU ID列表（如 ["100278222276", "100012043397"]）
    
    返回：
    精简的规格对比数据
    """
    logger.info(f"[Tool] 批量获取规格: {len(sku_ids)} 个SKU")
    
    products: list[Product] = []
    errors: list[str] = []
    
    try:
        success, access_token = init_jd_sdk()
        if not success:
            return {"products": [], "error": "京东官方API未配置或不可用"}
        
        from src.jd.api.rest.NewWareBaseproductGetRequest import NewWareBaseproductGetRequest
        
        request = NewWareBaseproductGetRequest('https://api.jd.com/routerjson', 80)
        request.ids = [int(id) for id in sku_ids]
        request.basefields = "wareInfo,specInfo"
        
        response = request.getResponse(access_token=access_token)
        
        if response and 'jingdong_new_ware_baseproduct_get_responce' in response:
            res = response['jingdong_new_ware_baseproduct_get_responce']
            product_list = res.get('listproductbase_result', [])
            
            for product in product_list:
                sku = str(product.get("skuId") or "").strip()
                if not sku:
                    continue
                spec_info = product.get("specInfo") or {}
                specs = {}
                if isinstance(spec_info, dict):
                    for k, v in spec_info.items():
                        if v is None:
                            continue
                        specs[str(k)] = str(v)
                title = str(product.get("wareName") or product.get("name") or "").strip() or f"JD商品{sku}"
                products.append(
                    Product(
                        id=f"jd_{sku}",
                        title=title,
                        price=1.0,
                        state=1,
                        platform="jd",
                        url=f"https://item.jd.com/{sku}.html",
                        brand=product.get("brandName"),
                        specs=specs,
                    )
                )
    except Exception as e:
        logger.error(f"[Tool] 批量规格查询失败: {e}")
        errors.append(str(e))

    if not products and errors:
        return {"products": [], "error": "; ".join(errors)}
    return {"products": products, "error": None}


# ==================== 工具8: justone_product_search - Justone商品搜索 ====================

@tool(
    category="research",
    tags=["搜索", "JustoneAPI", "价格", "销量"],
    display_name="Justone商品搜索（含价格、销量、服务保障）",
    icon="🔥",
    args_schema=JustoneProductSearchInput,
)
def justone_product_search(
    keyword: str,
    page: int = 1,
) -> Dict[str, Any]:
    """
    使用JustoneAPI搜索商品，返回包含价格、销量、好评关键词、服务保障的丰富数据。
    
    Args:
        keyword: 搜索关键词
        page: 页码（1-10）
    
    Returns:
        包含商品列表和错误状态的字典
    """
    logger.info(f"[Tool] JustoneAPI搜索: {keyword} | 页码: {page}")
    
    try:
        if not JUSTONE_API_KEY:
            return {"products": [], "error": "JustoneAPI未配置"}
        
        url = f"{JUSTONE_BASE_URL}/api/jd/search-item-list/v1"
        params = {
            "token": JUSTONE_API_KEY,
            "keyword": keyword,
            "page": str(page)
        }
        
        response = requests.get(url, params=params, timeout=10)
        result = response.json()
        
        if result.get('code') == 0:
            products_data = result.get("data", {}).get("products", []) or []

            products: list[Product] = []
            for item in products_data:
                sku = str(item.get("id") or "").strip()
                title = str(item.get("title") or item.get("name") or "").strip()
                if not sku or not title:
                    continue
                img = item.get("imgUrl") or item.get("imageUrl") or item.get("image") or None
                url_val = _safe_url(item.get("landUrl"), fallback=f"https://item.jd.com/{sku}.html")
                products.append(
                    Product(
                        id=f"jd_{sku}",
                        title=title,
                        price=_safe_price(item.get("price")),
                        state=1,
                        platform="jd",
                        url=url_val,
                        image_url=_safe_image_url(img),
                        shop_name=item.get("shopName"),
                        sales_count=_parse_sales(item.get("sales")),
                        good_comment_keywords=item.get("gcw", []),
                        promo_tags=item.get("promoTag"),
                        installment_info=item.get("foi"),
                    )
                )

            return {"products": products, "error": None}
        else:
            return {"products": [], "error": f"JustoneAPI返回错误: {result.get('message', '未知错误')}"}
            
    except Exception as e:
        logger.error(f"[Tool] JustoneAPI搜索失败: {e}")
        return {"products": [], "error": str(e)}


# ==================== 工具9: justone_product_full_detail - Justone商品完整详情 ====================

@tool(
    category="research",
    tags=["详情", "JustoneAPI", "服务保障", "促销信息", "排行榜"],
    display_name="Justone商品完整详情（服务保障+促销+排行榜）",
    icon="📊",
    args_schema=JustoneProductDetailInput,
)
def justone_product_full_detail(
    sku_id: str,
    existing_product: Product | None = None,
) -> Dict[str, Any]:
    """
    使用JustoneAPI获取商品完整详情，包括服务保障、促销信息、排行榜等。
    
    Args:
        sku_id: 商品SKU ID
    
    Returns:
        包含商品完整详情和错误状态的字典
    """
    logger.info(f"[Tool] JustoneAPI商品完整详情: {sku_id}")
    
    try:
        if not JUSTONE_API_KEY:
            return {"products": [], "error": "JustoneAPI未配置"}
        
        url = f"{JUSTONE_BASE_URL}/api/jd/get-item-detail/v1"
        params = {
            "token": JUSTONE_API_KEY,
            "itemId": sku_id
        }
        
        response = requests.get(url, params=params, timeout=10)
        result = response.json()
        
        if result.get('code') == 0:
            data = result.get('data', {})
            
            # 提取商品基础信息
            product = data.get('product', {})
            
            # 提取服务保障信息（stock.ir）
            stock = data.get('stock', {})
            service_icons = stock.get('ir', [])
            
            after_sales = []
            delivery = []
            increment = []
            
            for icon in service_icons:
                service_item = {
                    "name": icon.get('showName'),
                    "tip": icon.get('iconTip'),
                    "help_link": icon.get('helpLink'),
                    "icon_code": icon.get('iconCode')
                }
                
                icon_code = icon.get('iconCode', '')
                if 'tuihuo' in icon_code or 'price' in icon_code:  # 退货、价保
                    after_sales.append(service_item)
                elif 'sendpay' in icon_code or 'delivery' in icon_code:  # 物流
                    delivery.append(service_item)
                elif 'service_' in icon_code:  # 其他服务
                    increment.append(service_item)
            
            # 提取促销信息（promov2）
            promo_list = data.get('promov2', [])
            promo_info = []
            for promo in promo_list:
                pis = promo.get('pis', [])
                for pi in pis:
                    # 促销描述字段：'10'=促销标题, '18'=促销详情
                    promo_info.append({
                        "type": pi.get('promoType'),
                        "description": pi.get('10') or pi.get('18'),
                        "start_time": pi.get('st'),
                        "end_time": pi.get('d')
                    })
            
            # 提取排行榜信息（rankInfo）
            rank_list = data.get('rankInfo', [])
            rankings = []
            for r in rank_list:
                rankings.append({
                    "name": r.get('name'),
                    "rank_num": r.get('rankNum'),
                    "title": r.get('title'),
                    "jump_url": r.get('jump')
                })
            
            # 安全访问stock.D嵌套字典
            stock_d = stock.get('D') or {}

            title = str(product.get("skuName") or "").strip()
            if not title:
                title = f"JD商品{sku_id}"
            images = product.get("mainImages") or []
            first_img = images[0] if isinstance(images, list) and images else None

            p = _enrich_product(
                sku_id,
                existing_product,
                title=title,
                image_url=first_img,
                shop_name=stock_d.get("shopName"),
                brand=product.get("brandName"),
                category=product.get("productArea"),
                after_sales_info={"services": after_sales, "is_self_operated": stock_d.get("type") == 0},
                delivery_info={"services": delivery, "promise": stock.get("promiseResult"), "freight_info": stock.get("dcashDesc")},
                increment_service={"services": increment, "product_area": product.get("productArea"), "warranty": product.get("wserve")},
                promo_info={"promotions": promo_info, "has_gift": len(promo_info) > 0},
                rank_info={"rankings": rankings},
            )

            return {"products": [p], "error": None}
        else:
            return {"products": [], "error": f"JustoneAPI返回错误: {result.get('message', '未知错误')}"}
            
    except Exception as e:
        logger.error(f"[Tool] JustoneAPI商品详情失败: {e}")
        return {"products": [], "error": str(e)}
