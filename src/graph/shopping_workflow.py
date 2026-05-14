from __future__ import annotations

from langgraph.constants import END, START
from langgraph.graph import StateGraph
from langgraph.graph.state import CompiledStateGraph

from src.agents.analysis_agent import analysis_agent
from src.agents.recommendation_agent import recommendation_agent
from src.agents.search_agent import search_agent
from src.models.state import ShoppingState


def create_shopping_workflow_graph() -> CompiledStateGraph[ShoppingState]:
    graph = StateGraph(ShoppingState)

    graph.add_node("search", search_agent)
    graph.add_node("analysis", analysis_agent)
    graph.add_node("recommendation", recommendation_agent)

    graph.add_edge(START, "search")
    graph.add_edge("search", "analysis")
    graph.add_edge("analysis", "recommendation")
    graph.add_edge("recommendation", END)

    return graph.compile()

