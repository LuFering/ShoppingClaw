import logging
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
        
        # 合并 input_context 到 context
        if input_context:
            agent_config = input_context.get("agent_config")
            if isinstance(agent_config, dict):
                # Pydantic v2: 使用 model_copy 创建新实例并更新字段
                context = context.model_copy(update=agent_config)
            
            # 合并其他字段
            update_fields = {k: v for k, v in input_context.items() if k != "agent_config"}
            if update_fields:
                context = context.model_copy(update=update_fields)
        
        logging.debug(f"stream_messages: {context}")

        # 构建配置：LangGraph 会自动从 checkpointer 恢复 state
        input_config = {
            "configurable": {"thread_id": context.thread_id, "user_id": context.user_id},
            "recursion_limit": 100,
        }

        async for msg, metadata in graph.astream(
                input={"messages": messages},
                stream_mode="messages",
                context=context,
                config=input_config,
        ):
            yield msg, metadata
