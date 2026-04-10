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
        graph = await self.get_graph()
        context = self.context_schema()
        
        # 合并 input_context 到 context
        if input_context:
            agent_config = input_context.get("agent_config")
            if isinstance(agent_config, dict):
                context.update(agent_config)
            context.update(input_context)


        # 构建配置：LangGraph 会自动从 checkpointer 恢复 state
        input_config = {
            "configurable": {"thread_id": context.thread_id, "user_id": context.user_id},
            "recursion_limit": 100,
        }
        
        logging.info(f"[Graph Start] Context: {context.__dict__}")

        # 追踪节点数据流通
        async for chunk in graph.astream(
                input={"messages": messages},
                stream_mode="updates",
                context=context,
                config=input_config,
        ):
            for node_name, node_output in chunk.items():
                logging.info(f"[Node Flow] {node_name} -> Keys: {list(node_output.keys())}")

        # 返回消息流给前端
        async for msg, metadata in graph.astream(
                input={"messages": messages},
                stream_mode="messages",
                context=context,
                config=input_config,
        ):
            yield msg, metadata