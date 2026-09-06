"""Research Agent 工具的输入输出数据模型定义"""
from typing import List, Optional
from pydantic import BaseModel, Field


class JdDeepSearchInput(BaseModel):
    """京东深度搜索工具的输入参数"""
    keyword: str = Field(..., description="搜索关键词，如'iPhone 15'、'游戏本'")
    max_pages: int = Field(default=3, ge=1, le=10, description="最多爬取的页数（每页约60个商品）")
    max_empty_pages: int = Field(default=3, ge=1, le=5, description="连续空页数阈值，达到后提前停止")
    include_details: bool = Field(default=False, description="是否包含详细商品信息（会增加耗时）")


class JdProductDetailInput(BaseModel):
    """
    京东商品详情采集工具的输入参数
    
    重要提示：
    - 此工具调用jingdong.ware.productbigfield.get API获取规格参数和包装清单
    - 响应字段使用下划线命名: ware_qd(包装清单), prop_code(规格参数)
    - fetch_description参数暂未实现（需要其他API）
    """
    sku_id: str = Field(..., description="商品SKU ID字符串，如'100012345678'。工具内部会直接传给API（官方API要求sku_id=String类型）")
    fetch_specs: bool = Field(default=True, description="是否获取规格参数和包装清单（wareQD,propCode）")
    fetch_description: bool = Field(default=False, description="是否获取图文详情（暂未实现，请使用移动端详情API）")


class JdShopReliabilityInput(BaseModel):
    """京东店铺可靠性评估工具的输入参数"""
    shop_name: str = Field(..., description="店铺名称")
    shop_id: Optional[str] = Field(default=None, description="店铺ID（可选，有则更准确）")


class JdProductImagesInput(BaseModel):
    """
    京东商品图片查询工具的输入参数
    
    重要提示：
    - 此工具调用jingdong.ware.productimage.get API批量查询商品图片
    - sku_ids必须是Number[]类型，工具内部会自动将字符串列表转为整数数组
    - 支持批量查询，最多100个SKU
    - 响应数据包含主图标识(is_primary)和排序(orderSort)
    """
    sku_ids: List[str] = Field(..., description="商品SKU ID字符串列表，如['123456','789012']。工具内部会自动转为整数数组[123456,789012]传给API（官方API要求sku_id=Number[]类型）", min_length=1, max_length=100)


class JdProductBasicInput(BaseModel):
    """
    京东商品基础信息查询工具的输入参数
    
    重要提示：
    - basefields参数必须包含至少一个有效字段，否则API返回空列表
    - 可用字段: name(商品名), isDelete(上下架状态)
    - API会自动返回 skuId 和 url 字段，无需指定
    - 工具内部会将字符串SKU ID列表转为整数数组传给SDK（官方API要求ids=Number[]类型）
    """
    sku_ids: List[str] = Field(..., description="商品SKU ID字符串列表，如['123456','789012']。工具内部会自动转为整数数组[123456,789012]传给API（官方API要求ids=Number[]类型）", min_length=1)
    fields: Optional[List[str]] = Field(
        default=None, 
        description="需要返回的字段列表。可用值: ['name', 'isDelete']。默认返回['name', 'isDelete']。API会自动附加skuId和url字段。"
    )


class JdProductMobileDetailInput(BaseModel):
    """
    京东移动端商品详情查询工具的输入参数
    
    重要提示：
    - 此工具调用jingdong.new.ware.mobilebigfield.get API获取HTML富文本详情
    - skuid参数必须是Number类型，工具内部会自动转换
    - fields参数无效，API不支持字段过滤，会返回所有字段
    - 响应数据在result字段中，包含完整的HTML内容
    """
    sku_id: str = Field(..., description="商品SKU ID字符串，如'123456'。工具内部会自动转为整数123456传给API（官方API要求skuid=Number类型）")
    fields: Optional[List[str]] = Field(
        default=None,
        description="此参数无效，官方API不支持字段过滤，会返回所有字段（wareQD,propCode,wdis等）"
    )


class JustoneProductSearchInput(BaseModel):
    """JustoneAPI商品搜索工具的输入参数"""
    keyword: str = Field(..., description="搜索关键词")
    page: int = Field(default=1, ge=1, le=10, description="页码")


class JustoneProductDetailInput(BaseModel):
    """JustoneAPI商品详情工具的输入参数"""
    sku_id: str = Field(..., description="商品SKU ID")