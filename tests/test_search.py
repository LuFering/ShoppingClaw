"""Search tool unit tests."""

import pytest

from src.models.product import Product
from src.tools.search import search


def test_search_default_all_platforms():
    results = search("手机", platforms=None, limit=10)
    assert isinstance(results, list)
    assert len(results) == 3
    assert {p.platform for p in results} == {"jd", "taobao", "pdd"}


def test_search_single_platform():
    results = search("手机", platforms=["jd"], limit=10)
    assert len(results) == 1
    assert all(p.platform == "jd" for p in results)


def test_search_multiple_platforms():
    results = search("手机", platforms=["jd", "taobao"], limit=10)
    assert len(results) == 2
    assert {p.platform for p in results} == {"jd", "taobao"}


def test_search_empty_platforms():
    results = search("手机", platforms=[], limit=10)
    assert results == []


def test_invalid_query_empty():
    with pytest.raises(ValueError):
        search("", platforms=["jd"], limit=10)


def test_invalid_query_whitespace():
    with pytest.raises(ValueError):
        search("   ", platforms=["jd"], limit=10)


def test_invalid_query_length():
    with pytest.raises(ValueError):
        search("a" * 101, platforms=["jd"], limit=10)


# def test_invalid_limit():
#     for bad_limit in (0, -1, 101):
#         with pytest.raises(ValueError):
#             search("手机", platforms=["jd"], limit=bad_limit)

# By Claude
@pytest.mark.parametrize("bad_limit", [0, -1, 101])
def test_invalid_limit(bad_limit: int):
    with pytest.raises(ValueError):
        search("手机", platforms=["jd"], limit=bad_limit)

def test_return_type():
    results = search("手机", platforms=["jd"], limit=10)
    assert all(isinstance(item, Product) for item in results)
