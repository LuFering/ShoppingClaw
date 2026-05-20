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

# 京东SDK静态导入
import jd.api
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
)

logger = logging.getLogger(__name__)

# JustoneAPI配置
JUSTONE_API_KEY = os.getenv("JUSTONE_API_KEY")
JUSTONE_BASE_URL = os.getenv("JUSTONE_BASE_URL", "https://api.justoneapi.com")

# JD SDK singleton state — avoids re-initializing on every tool call
_jd_initialized: bool = False
_jd_access_token: str | None = None

# In-memory cache for product details (keyed by sku_id)
# Prevents re-fetching the same SKU within a single request
_detail_cache: dict[str, dict] = {}

# In-memory cache for search results (keyed by "keyword:page")
# Prevents redundant API calls when researcher retries or searches overlapping keywords
_search_cache: dict[str, dict] = {}


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


def init_jd_sdk():
    """初始化京东SDK认证（**单例模式**，仅首次调用时真正初始化）"""
    global _jd_initialized, _jd_access_token

    if _jd_initialized:
        return True, _jd_access_token

    # 从环境变量读取配置
    app_key = os.getenv("JD_APP_KEY")
    app_secret = os.getenv("JD_APP_SECRET")
    _jd_access_token = os.getenv("JD_ACCESS_TOKEN")

    if not app_key or not app_secret:
        logger.warning("[JD API] 未配置JD_APP_KEY或JD_APP_SECRET")
        return False, None

    jd.setDefaultAppInfo(app_key, app_secret)
    _jd_initialized = True
    logger.info(f"[JD API] SDK初始化完成（首次）| Access Token: {'已配置' if _jd_access_token else '未配置'}")
    return True, _jd_access_token


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
            return {
                "keyword": keyword,
                "total_products": 0,
                "pages_crawled": 0,
                "products": [],
                "error": "未配置JD_APP_KEY或JD_APP_SECRET",
            }
        
        from jd.api.rest.SearchWareRequest import SearchWareRequest
        
        all_products = []
        
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
                    content = item.get('Content', {})
                    product = {
                        "sku_id": str(item.get('wareid', '')),
                        "title": unquote(content.get('warename', '')),
                        "image_url": content.get('imageurl', ''),
                        "good_rate": item.get('good', ''),
                        "shop_id": item.get('shop_id', ''),
                    }
                    all_products.append(product)
            
            logger.info(f"[Tool] 第{page}页获取 {len(all_products)} 个商品")
        
        return {
            "keyword": keyword,
            "total_products": len(all_products),
            "pages_crawled": page,
            "products": all_products,
            "error": None,
        }
    
    except Exception as e:
        logger.error(f"[Tool] 京东API搜索失败: {e}")
        return {
            "keyword": keyword,
            "total_products": 0,
            "pages_crawled": 0,
            "products": [],
            "error": str(e),
        }


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
            return {"sku_id": sku_id, "error": "未配置JD_APP_KEY或JD_APP_SECRET"}
        
        from jd.api.rest.WareProductbigfieldGetRequest import WareProductbigfieldGetRequest
        
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
        if response and 'jingdong_ware_productbigfield_get_responce' in response:
            res = response['jingdong_ware_productbigfield_get_responce']
            
            # 提取各个字段的数据
            result = {
                "sku_id": sku_id,
                "wareQD": res.get('wareQD', ''),  # 包装清单
                "propCode": res.get('propCode', ''),  # 规格参数
                "wdis": res.get('wdis', ''),  # 商品介绍
                "error": None,
            }
            return result
        
        return {"sku_id": sku_id, "error": "API返回数据格式异常"}
    
    except Exception as e:
        logger.error(f"[Tool] 京东API商品详情失败: {e}")
        return {"sku_id": sku_id, "error": str(e)}


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
    
    return {
        "shop_name": shop_name,
        "shop_id": shop_id,
        "error": "API暂未实现",
    }


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
            return {"sku_ids": sku_ids, "error": "未配置JD_APP_KEY或JD_APP_SECRET"}
        
        from jd.api.rest.WareProductimageGetRequest import WareProductimageGetRequest
        
        request = WareProductimageGetRequest('https://api.jd.com/routerjson', 80)
        # 将字符串列表转为整数列表
        request.sku_id = [int(sku_id) for sku_id in sku_ids]
        
        response = request.getResponse()  # 无需access_token
        
        # 解析返回数据
        if response and 'jingdong_ware_productimage_get_responce' in response:
            res = response['jingdong_ware_productimage_get_responce']
            image_path_list = res.get('image_path_list', [])
            
            # 构建结果字典
            result = {}
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
                
                result[sku_id_str] = {
                    "total_images": len(image_info),
                    "primary_image": next((img["url"] for img in image_info if img["is_primary"]), None),
                    "images": image_info,
                }
            
            return {
                "sku_ids": sku_ids,
                "results": result,
                "error": None,
            }
        
        return {"sku_ids": sku_ids, "error": "API返回数据格式异常"}
    
    except Exception as e:
        logger.error(f"[Tool] 京东API商品图片查询失败: {e}")
        return {"sku_ids": sku_ids, "error": str(e)}


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
            return {"sku_ids": sku_ids, "error": "未配置JD_APP_KEY或JD_APP_SECRET"}
        
        from jd.api.rest.NewWareBaseproductGetRequest import NewWareBaseproductGetRequest
        
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
            
            # 构建结果字典
            result = {}
            for product in product_list:
                sku_id_str = str(product.get('skuId', ''))
                result[sku_id_str] = {
                    "name": product.get('name', ''),  # 注意：字段名是name不是pname
                    "is_delete": product.get('isDelete', ''),  # 1=上架, 0=下架
                    "url": product.get('url', ''),
                }
            
            return {
                "sku_ids": sku_ids,
                "results": result,
                "error": None,
            }
        
        return {"sku_ids": sku_ids, "error": "API返回数据格式异常"}
    
    except Exception as e:
        logger.error(f"[Tool] 京东API商品基础信息查询失败: {e}")
        return {"sku_ids": sku_ids, "error": str(e)}


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
            return {"sku_id": sku_id, "error": "未配置JD_APP_KEY或JD_APP_SECRET"}
        
        from jd.api.rest.NewWareMobilebigfieldGetRequest import NewWareMobilebigfieldGetRequest
        
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
            
            return {
                "sku_id": sku_id,
                "html_content": html_content,
                "content_length": len(html_content),
                "error": None,
            }
        
        return {"sku_id": sku_id, "error": "API返回数据格式异常"}
    
    except Exception as e:
        logger.error(f"[Tool] 京东API移动端商品详情失败: {e}")
        return {"sku_id": sku_id, "error": str(e)}


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

    # 缓存命中 — 同一关键词+页码在一次请求中可能被重复搜索
    cache_key = f"{keyword}:{page}"
    cached = _search_cache.get(cache_key)
    if cached is not None:
        logger.info(f"[Tool] 搜索缓存命中: {cache_key}")
        return cached

    products = []
    
    # 1. 调用官方API获取基础数据（好评率、店铺ID）
    try:
        success, access_token = init_jd_sdk()
        if success:
            from jd.api.rest.SearchWareRequest import SearchWareRequest
            
            request = SearchWareRequest('https://api.jd.com/routerjson', 80)
            request.key = quote(keyword)
            request.page = str(page)
            
            response = request.getResponse(access_token=access_token)
            
            if response and 'jingdong_search_ware_responce' in response:
                res = response['jingdong_search_ware_responce']
                paragraph = res.get('Paragraph', [])
                
                for item in paragraph:
                    content = item.get('Content', {})
                    products.append({
                        "id": f"jd_{item.get('wareid')}",  # 符合Product.id格式
                        "title": content.get('warename', ''),
                        "image_url": f"https://img10.360buyimg.com/n1/{content.get('imageurl', '')}",
                        "good_rate": item.get('good'),  # 额外字段
                        "shop_id": item.get('shop_id'),
                        "category_id": item.get('catid'),
                        "platform": "jd"
                    })
    except Exception as e:
        logger.warning(f"[Tool] 官方API搜索失败: {e}")
    
    # 2. 如果需要价格，调用JustoneAPI补充数据
    if need_price and JUSTONE_API_KEY and len(products) > 0:
        try:
            url = f"{JUSTONE_BASE_URL}/api/jd/search-item-list/v1"
            params = {
                "token": JUSTONE_API_KEY,
                "keyword": keyword,
                "page": str(page)
            }
            
            response = requests.get(url, params=params, timeout=10)
            result = response.json()
            
            if result.get('code') == 0:
                justone_products = result.get('data', {}).get('products', [])
                
                # 按ID匹配，合并数据
                justone_map = {str(p['id']): p for p in justone_products}
                
                for product in products:
                    sku_id = product['id'].replace('jd_', '')  # 去掉前缀匹配
                    if sku_id in justone_map:
                        j = justone_map[sku_id]
                        
                        # 映射到Product模型字段
                        product['price'] = float(j.get('price', 0)) if j.get('price') else None
                        product['shop_name'] = j.get('shopName')
                        product['sales_count'] = _parse_sales(j.get('sales'))  # 转换为int
                        product['good_comment_keywords'] = j.get('gcw', [])
                        product['installment_info'] = j.get('foi')
                        product['promo_tags'] = j.get('promoTag')
                        product['url'] = j.get('landUrl')
                        
        except Exception as e:
            logger.warning(f"[Tool] JustoneAPI搜索失败: {e}")
    
    result = {
        "status": "success",
        "count": len(products),
        "products": products  # 已是Product兼容结构
    }
    _search_cache[cache_key] = result
    return result


# ==================== 工具9: get_product_full_detail - 完整详情（官方+Justone） ====================

@tool(
    category="research",
    tags=["详情", "整合", "服务保障", "促销信息", "排行榜"],
    display_name="商品完整详情（官方+Justone整合）",
    icon="📊",
)
def get_product_full_detail(sku_id: str) -> Dict[str, Any]:
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

    # 缓存命中 — 同一SKU可能在一次请求中被多次查询
    cached = _detail_cache.get(sku_id)
    if cached is not None:
        logger.info(f"[Tool] 商品详情缓存命中: {sku_id}")
        return cached

    # 初始化Product兼容结构
    detail = {
        "id": f"jd_{sku_id}",
        "platform": "jd",
        "title": None,
        "price": None,
        "url": None,
        "image_url": None,
        "shop_name": None,
        "brand": None,
        "category": None,
        "key_specs": {},
        "after_sales_info": {},
        "delivery_info": {},
        "increment_service": {},
        "promo_info": {},
        "rank_info": {}
    }
    
    # 1. 基础信息 + 规格参数（官方API）
    try:
        success, access_token = init_jd_sdk()
        if success:
            from jd.api.rest.NewWareBaseproductGetRequest import NewWareBaseproductGetRequest
            
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
                        detail['key_specs'] = {
                            k: v for k, v in spec_info.items() 
                            if isinstance(v, str) and len(v) < 100  # 过滤长文本
                        }
    except Exception as e:
        logger.warning(f"[Tool] 官方API基础信息失败: {e}")
    
    # 2. 商品图片（官方API）
    try:
        success, access_token = init_jd_sdk()
        if success:
            from jd.api.rest.WareProductimageGetRequest import WareProductimageGetRequest
            
            request = WareProductimageGetRequest('https://api.jd.com/routerjson', 80)
            request.skuId = int(sku_id)
            
            response = request.getResponse(access_token=access_token)
            
            if response and 'jingdong_ware_productimage_get_responce' in response:
                res = response['jingdong_ware_productimage_get_responce']
                images = res.get('imageList', [])
                if images:
                    detail['image_url'] = images[0].get('url')  # 主图
    except Exception as e:
        logger.warning(f"[Tool] 官方API图片失败: {e}")
    
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

    # 写入缓存
    _detail_cache[sku_id] = detail
    return detail


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
    
    specs_data = []
    
    try:
        success, access_token = init_jd_sdk()
        if not success:
            return {
                "status": "error",
                "message": "未配置JD_APP_KEY或JD_APP_SECRET"
            }
        
        from jd.api.rest.NewWareBaseproductGetRequest import NewWareBaseproductGetRequest
        
        request = NewWareBaseproductGetRequest('https://api.jd.com/routerjson', 80)
        request.ids = [int(id) for id in sku_ids]
        request.basefields = "wareInfo,specInfo"
        
        response = request.getResponse(access_token=access_token)
        
        if response and 'jingdong_new_ware_baseproduct_get_responce' in response:
            res = response['jingdong_new_ware_baseproduct_get_responce']
            product_list = res.get('listproductbase_result', [])
            
            for product in product_list:
                specs_data.append({
                    "sku_id": product.get('skuId'),
                    "brand": product.get('brandName'),
                    "model": product.get('model'),
                    "specs": product.get('specInfo', {})
                })
    except Exception as e:
        logger.error(f"[Tool] 批量规格查询失败: {e}")
        return {
            "status": "error",
            "message": str(e)
        }
    
    return {
        "status": "success",
        "count": len(specs_data),
        "products": specs_data
    }


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
            return {
                "keyword": keyword,
                "total_products": 0,
                "products": [],
                "error": "未配置JUSTONE_API_KEY",
            }
        
        url = f"{JUSTONE_BASE_URL}/api/jd/search-item-list/v1"
        params = {
            "token": JUSTONE_API_KEY,
            "keyword": keyword,
            "page": str(page)
        }
        
        response = requests.get(url, params=params, timeout=10)
        result = response.json()
        
        if result.get('code') == 0:
            products_data = result.get('data', {}).get('products', [])
            
            products = []
            for item in products_data:
                # 安全转换价格
                price_val = item.get('price')
                try:
                    price_float = float(price_val) if price_val else None
                except (ValueError, TypeError):
                    price_float = None
                
                product = {
                    "sku_id": str(item.get('id', '')),  # 确保字符串类型
                    "title": item.get('title'),
                    "price": price_float,
                    "image_url": f"https://img10.360buyimg.com/n1/{item.get('imageUrl', '')}",
                    "shop_name": item.get('shopName'),
                    "sales": item.get('sales'),
                    "month_sales": item.get('monthSales'),
                    "good_comment_keywords": item.get('gcw', []),
                    "recommendation": item.get('gct'),
                    "url": item.get('landUrl'),
                    "promo_tags": item.get('promoTag'),
                    "installment_info": item.get('foi'),
                }
                products.append(product)
            
            return {
                "keyword": keyword,
                "page": page,
                "total_products": len(products),
                "products": products,
                "error": None,
            }
        else:
            return {
                "keyword": keyword,
                "total_products": 0,
                "products": [],
                "error": f"JustoneAPI返回错误: {result.get('message', '未知错误')}",
            }
            
    except Exception as e:
        logger.error(f"[Tool] JustoneAPI搜索失败: {e}")
        return {
            "keyword": keyword,
            "total_products": 0,
            "products": [],
            "error": str(e),
        }


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
            return {"sku_id": sku_id, "error": "未配置JUSTONE_API_KEY"}
        
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
            
            return {
                "sku_id": sku_id,
                "basic_info": {
                    "sku_id": product.get('skuId'),
                    "title": product.get('skuName'),
                    "brand": product.get('brandName'),
                    "model": product.get('model'),
                    "category": product.get('productArea'),
                    "shop_name": stock_d.get('shopName'),
                    "is_self_operated": stock_d.get('type') == 0,
                },
                "after_sales_info": {
                    "services": after_sales,
                    "shop_name": stock_d.get('shopName'),
                    "is_self_operated": stock_d.get('type') == 0
                },
                "delivery_info": {
                    "services": delivery,
                    "promise": stock.get('promiseResult'),
                    "freight_info": stock.get('dcashDesc')
                },
                "increment_service": {
                    "services": increment,
                    "product_area": product.get('productArea'),
                    "warranty": product.get('wserve')
                },
                "promo_info": {
                    "promotions": promo_info,
                    "has_gift": len(promo_info) > 0
                },
                "rank_info": {
                    "rankings": rankings
                },
                "main_images": product.get('mainImages', []),
                "error": None,
            }
        else:
            return {
                "sku_id": sku_id,
                "error": f"JustoneAPI返回错误: {result.get('message', '未知错误')}"
            }
            
    except Exception as e:
        logger.error(f"[Tool] JustoneAPI商品详情失败: {e}")
        return {"sku_id": sku_id, "error": str(e)}
