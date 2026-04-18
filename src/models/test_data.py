"""测试用商品样本数据。"""

from src.models.product import Product

SAMPLE_PRODUCTS = [
    Product(
        id="jd_001",
        title="京东示例手机 A",
        price=3999.0,
        platform="jd",
        url="https://example.com/jd/001",
    ),
    Product(
        id="jd_002",
        title="京东示例手机 B",
        price=2999.0,
        platform="jd",
        url="https://example.com/jd/002",
    ),
    Product(
        id="taobao_001",
        title="淘宝示例手机 A",
        price=1999.0,
        platform="taobao",
        url="https://example.com/taobao/001",
    ),
    Product(
        id="taobao_002",
        title="淘宝示例手机 B",
        price=2599.0,
        platform="taobao",
        url="https://example.com/taobao/002",
    ),
    Product(
        id="pdd_001",
        title="拼多多示例手机 A",
        price=1499.0,
        platform="pdd",
        url="https://example.com/pdd/001",
    ),
    Product(
        id="pdd_002",
        title="拼多多示例手机 B",
        price=1799.0,
        platform="pdd",
        url="https://example.com/pdd/002",
    ),
]
