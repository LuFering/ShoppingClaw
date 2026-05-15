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

    async def get_info(self) -> dict:
        """返回 agent 的基本信息"""
        return {
            "id": self.__class__.__name__,
            "name": self.name,
            "description": self.description,
            "capabilities": self.capabilities,
            "examples": getattr(self, "examples", []),
            "has_checkpointer": self.checkpointer is not None,
            "configurable_items": [],
        }

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

        # 返回消息流给前端：
        # - messages: token 级正文和 reasoning_content
        # - updates: 节点级别的状态更新，用于捕获工具执行后的模型总结
        logging.info(f"[Stream Start] graph.astream 开始迭代 (mode: messages + updates)")
        async for chunk in graph.astream(
                input={"messages": messages},
                stream_mode=["messages", "updates"],
                context=context,
                config=input_config,
        ):
            # LangGraph 混合模式返回的是 (namespace, data) 元组
            if isinstance(chunk, tuple) and len(chunk) == 2:
                namespace, data = chunk
                # 如果 data 是字典（updates），尝试清洗其中的 Overwrite 对象
                if isinstance(data, dict):
                    cleaned_data = {}
                    for k, v in data.items():
                        if hasattr(v, 'model_dump'):
                            cleaned_data[k] = v.model_dump()
                        elif isinstance(v, (str, int, float, bool, list)) or v is None:
                            cleaned_data[k] = v
                        else:
                            cleaned_data[k] = f"<{type(v).__name__}>"
                    yield cleaned_data, {"stream_mode": "updates", "namespace": namespace}
                else:
                    # messages 模式通常直接返回消息对象
                    yield data, {"stream_mode": "messages", "namespace": namespace}
            else:
                # 兼容单一模式
                yield chunk, {}
        logging.info(f"[Stream End] graph.astream 迭代完成")
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
