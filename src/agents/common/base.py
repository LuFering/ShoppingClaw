import logging
from abc import abstractmethod

from langgraph.graph.state import CompiledStateGraph

from src.agents.common.context import BaseContext


class BaseAgent:
    name = "base_agent"
    description = "base_agent"
    capabilities: list[str] = []
    context_schema: type[BaseContext] = BaseContext

    def __init__(self, **kwargs):
        self.graph = None
        self.checkpointer = None
        self._checkpointer_cm = None

    @property
    def module_name(self)->str:
        """获取agent模块名"""
        return self.__class__.__module__.split(".")[-2]


    @abstractmethod
    def get_graph(self, **kwargs) -> CompiledStateGraph:
        pass

    async def stream_messages(self, messages: list[str], input_context=None, **kwargs):
        graph = await self.get_graph() #初始编译图
        context = self.context_schema()
        
        # 合并 input_context 到 context
        if input_context:
            agent_config = input_context.get("agent_config")
            if isinstance(agent_config, dict):
                context.update(agent_config)
            context.update(input_context) #将input_context更新至context传入agent


        # 构建配置：LangGraph 会自动从 checkpointer 恢复 state
        input_config = { #input_config 是 LangGraph 的执行配置
            "configurable": {"thread_id": context.thread_id, "user_id": context.user_id},# 传给 checkpointer，用于恢复对话历史
            "recursion_limit": 100,
        }
        
        # logging.info(f"[Graph Start] Context: {context.__dict__}")  # 注释掉：避免输出 system_prompt

        # 返回消息流给前端（直接使用 messages 模式，保持状态连续性）
        async for msg, metadata in graph.astream(
                input={"messages": messages},
                stream_mode="messages",
                context=context,
                config=input_config,
        ):
            yield msg, metadata
    async def invoke_messages(self,messages:list[str],input_context=None,**kwargs):
        graph=await self.get_graph()
        context=self.context_schema()
        # 合并 input_context 到 context
        if input_context:
            agent_config = input_context.get("agent_config")
            if isinstance(agent_config, dict):
                context.update(agent_config)
            context.update(input_context)  # 将input_context更新至context传入agent

        # 构建配置：LangGraph 会自动从 checkpointer 恢复 state
        input_config = {  # input_config 是 LangGraph 的执行配置
            "configurable": {"thread_id": context.thread_id, "user_id": context.user_id},
            # 传给 checkpointer，用于恢复对话历史
            "recursion_limit": 100,
        }
        msg=await graph.ainvoke(
            {"messages": messages},
            context=context,
            config=input_config,
        )
        return msg
