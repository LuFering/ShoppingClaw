from src.agents.common.base import BaseAgent
from src.agents.mainagent.context import MainContext
from src.agents.mainagent.agent_demo import create_main_agent


class MainAgent(BaseAgent):
    name="核心智能体"
    description = "具备规划、深度分析和子智能体协作能力的智能体，可以处理复杂的多步骤任务"
    context_schema =MainContext
    tools=[]

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.graph=None
        self.checkpointer=None

    async def get_tools(self):
        return self.tools
    
    async def get_graph(self, **kwargs):
        """获取或创建 Agent 图"""
        # 如果 graph 已经存在,直接返回(单例模式)
        if self.graph is not None:
            return self.graph
        
        # 创建新的 graph
        config = {
            "model": "qwen2.5:3b",
            "tools": self.tools,
        }
        
        # 如果有 checkpointer,添加到配置
        if self.checkpointer:
            config["checkpointer"] = self.checkpointer
        
        # 调用工厂函数创建 graph
        self.graph = create_main_agent(**config)
        
        return self.graph
