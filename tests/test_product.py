"""Product 模型校验与类型行为单测。"""

import pytest
from pydantic import ValidationError

from src.models.product import Product
from src.models.test_data import SAMPLE_PRODUCTS


def test_sample_products_count_and_platforms():
    assert len(SAMPLE_PRODUCTS) == 6
    by_platform = {p.platform for p in SAMPLE_PRODUCTS}
    assert by_platform == {"jd", "taobao", "pdd"}
    assert sum(1 for p in SAMPLE_PRODUCTS if p.platform == "jd") == 2
    assert sum(1 for p in SAMPLE_PRODUCTS if p.platform == "taobao") == 2
    assert sum(1 for p in SAMPLE_PRODUCTS if p.platform == "pdd") == 2


def test_required_fields_missing_raises():
    with pytest.raises(ValidationError) as exc_info:
        Product(
            title="仅标题",
            price=99.0,
            platform="jd",
            url="https://example.com/x",
        )
    # assert "id" in str(exc_info.value).lower() or "id" in exc_info.value.errors()[0]["loc"]
    errors = exc_info.value.errors()
    assert any(e["loc"] == ("id",) for e in errors)

def test_optional_fields_can_be_none():
    product = Product(
    id="jd_minimal_1",
    title="最小必填商品",
    price=19.9,
    platform="jd",
    url="https://item.jd.com/minimal.html",
    )
    assert product.rating is None
    assert product.specs == {}


def test_specs_default_is_isolated():
    """避免可变默认 dict 在实例间共享。"""
    first = Product(
        id="jd_a",
        title="A",
        price=10.0,
        platform="jd",
        url="https://example.com/a",
    )
    second = Product(
        id="jd_b",
        title="B",
        price=11.0,
        platform="jd",
        url="https://example.com/b",
    )
    first.specs["k"] = "v"
    assert "k" not in second.specs


def test_price_must_be_positive():
    with pytest.raises(ValidationError):
        Product(
            id="jd_bad_price",
            title="无效价",
            price=0,
            platform="jd",
            url="https://example.com/x",
        )

def test_rating_boundary_valid():
    for valid_rating in (0.0, 2.5, 5.0):
        p = Product(
            id="jd_rating_ok",
            title="评分边界",
            price=50.0,
            platform="jd",
            url="https://example.com/item",
            rating=valid_rating,
        )
        assert p.rating == valid_rating

def test_rating_range():
    with pytest.raises(ValidationError):
        Product(
            id="jd_bad_rating",
            title="评分越界",
            price=50.0,
            platform="jd",
            url="https://example.com/x",
            rating=5.1,
        )


def test_platform_literal():
    with pytest.raises(ValidationError):
        Product(
            id="xx_1",
            title="平台非法",
            price=50.0,
            platform="amazon",  # type: ignore[arg-type]
            url="https://example.com/x",
        )


def test_field_type_validation():
    """price 的 str 数字会被 Pydantic 合法转换；用不可转换的类型测校验。"""
    with pytest.raises(ValidationError):
        Product(
            id="jd_type",
            title="类型错误",
            price=99.0,
            platform="jd",
            url="https://example.com/x",
            comment_count="很多",  # type: ignore[arg-type]
        )
