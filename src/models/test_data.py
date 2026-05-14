from src.models.product import Product

SAMPLE_PRODUCTS = [
    Product(
        id="jd_sample_1",
        title="Apple iPhone 15 128GB",
        price=5999.0,
        state=1,
        platform="jd",
        url="https://item.jd.com/1.html",
    ),
    Product(
        id="jd_sample_2",
        title="小米 14 12GB+256GB",
        price=3999.0,
        state=1,
        platform="jd",
        url="https://item.jd.com/2.html",
    ),
    Product(
        id="taobao_sample_1",
        title="华为 Mate 60 12GB+512GB",
        price=5999.0,
        state=1,
        platform="taobao",
        url="https://item.taobao.com/item.htm?id=1",
    ),
    Product(
        id="taobao_sample_2",
        title="Apple iPhone 15 Pro 256GB",
        price=7999.0,
        state=1,
        platform="taobao",
        url="https://item.taobao.com/item.htm?id=2",
    ),
    Product(
        id="pdd_sample_1",
        title="百亿补贴：Apple iPhone 15",
        price=5799.0,
        state=1,
        platform="pdd",
        url="https://mobile.yangkeduo.com/goods.html?goods_id=1",
    ),
    Product(
        id="pdd_sample_2",
        title="百亿补贴：小米 14",
        price=3899.0,
        state=1,
        platform="pdd",
        url="https://mobile.yangkeduo.com/goods.html?goods_id=2",
    ),
]

