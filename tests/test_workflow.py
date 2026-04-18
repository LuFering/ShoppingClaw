from __future__ import annotations

import pytest

from src.agents import analysis_agent, recommendation_agent, search_agent
from src.models.product import Product
from src.models.state import build_shopping_state


def test_single_path_workflow():
    state = build_shopping_state(query="iPhone 15", platform="jd")

    r1 = search_agent(state)
    assert "error" not in r1
    assert "products" in r1
    assert isinstance(r1["products"], list)
    assert len(r1["products"]) >= 0
    assert all(isinstance(p, Product) for p in r1["products"])
    state.update(r1)
    assert "products" in state

    r2 = analysis_agent(state)
    assert "analysis_report" in r2
    assert isinstance(r2["analysis_report"], str)
    state.update(r2)
    assert "analysis_report" in state

    r3 = recommendation_agent(state)
    assert "error" not in r3
    assert "recommendations" in r3 and "answer" in r3
    assert isinstance(r3["recommendations"], list)
    assert all(isinstance(p, Product) for p in r3["recommendations"])
    state.update(r3)
    assert "recommendations" in state and "answer" in state


def test_empty_query_workflow():
    state = build_shopping_state(query="   ", platform="jd")
    r1 = search_agent(state)
    assert "error" in r1
    assert isinstance(r1["error"], str)


def test_empty_products_workflow():
    state = build_shopping_state(query="SomeNonExistingProductNameXYZ", platform="jd")
    r1 = search_agent(state)
    state.update(r1)
    # 模拟无商品：覆盖 products 为 []
    state["products"] = []

    r2 = analysis_agent(state)
    assert "analysis_report" in r2
    assert isinstance(r2["analysis_report"], str)
    state.update(r2)

    r3 = recommendation_agent(state)
    assert "error" not in r3
    assert r3["recommendations"] == []
    assert isinstance(r3["answer"], str)


def test_compare_failure_workflow(monkeypatch: pytest.MonkeyPatch):
    state = build_shopping_state(query="iPhone 15", platform="jd")
    r1 = search_agent(state)
    state.update(r1)
    r2 = analysis_agent(state)
    state.update(r2)

    # 强制 compare_products 抛异常，验证异常路径
    import importlib

    recommendation_agent_mod = importlib.import_module("src.agents.recommendation_agent")

    def boom(_):
        raise RuntimeError("compare failed")

    monkeypatch.setattr(recommendation_agent_mod, "compare_products", boom)

    r3 = recommendation_agent(state)
    assert "error" in r3
    assert "failed" in r3["error"]


if  __name__ =="__main__":
    pytest.main([__file__,"-v"])