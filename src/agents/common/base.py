from abc import abstractmethod

from langgraph.graph.state import CompiledStateGraph

from src.agents.common.context import BaseContext


class BaseAgent:
    name = "base_agent"
    description = "base_agent"
    tools: list[str] = []
    context_schema: type[BaseContext] = BaseContext

    def __init__(self, **kwargs):
        self.graph = None
        self.checkpointer = None
        self._checkpointer_cm = None

    @abstractmethod
    def get_graph(self, **kwargs) -> CompiledStateGraph:
        pass

    async def stream_messages(self, messages: list[str], input_context=None, **kwargs):
        graph = await self.get_graph()
        context = self.context_schema()
        agent_config = input_context.get("agent_config")
        if isinstance(agent_config, dict):
            context.update(agent_config)
        context.update(input_context)
        input_config = {
            "configurable": {"thread_id": context.thread_id, "user_id": context.uesr_id},
            "recursion_limit": 100,
        }

        async for msg, metadata in graph.astream(
                input={"messages": messages},
                stream_mode="messages",
                context=context,
                config=input_config,
        ):
            yield msg, metadata #yield,懒加载，会将函数stream_messages封装成生成器
