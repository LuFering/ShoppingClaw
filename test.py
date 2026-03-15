from langchain_ollama import ChatOllama
from langchain_core.tools import tool
from typing import TypedDict
from langgraph.graph import StateGraph, START, END

# 定义工具
@tool
def search(query: str) -> str:
    """模拟搜索工具"""
    return f"搜索结果 for {query}: 找到了一些信息！"

# 定义状态
class State(TypedDict):
    input: str
    output: str
    needs_search: bool

# 节点：调用 LLM 判断是否需要搜索
def call_llm(state: State) -> State:
    llm = ChatOllama(model="deepseek-r1:1.5b")
    prompt = f"用户输入: {state['input']}\n是否需要搜索？回答 'yes' 或 'no'。"
    response = llm.invoke(prompt).content
    state["needs_search"] = response.lower() == "yes"
    state["output"] = "正在处理..."
    return state

# 节点：执行搜索
def call_search(state: State) -> State:
    result = search.invoke(state["input"])
    state["output"] = result
    return state

# 节点：直接回答
def direct_answer(state: State) -> State:
    state["output"] = f"直接回答: {state['input']}"
    return state

# 条件函数
def route(state: State) -> str:
    return "call_search" if state["needs_search"] else "direct_answer"

# 创建图
workflow = StateGraph(State)
workflow.add_node("call_llm", call_llm)
workflow.add_node("call_search", call_search)
workflow.add_node("direct_answer", direct_answer)
workflow.add_edge(START, "call_llm")
workflow.add_conditional_edges("call_llm", route, {
    "call_search": "call_search",
    "direct_answer": "direct_answer"
})
workflow.add_edge("call_search", END)
workflow.add_edge("direct_answer", END)

# 编译和运行
graph = workflow.compile()
result = graph.invoke({"input": "今天的天气", "output": "", "needs_search": False})
print(result)
