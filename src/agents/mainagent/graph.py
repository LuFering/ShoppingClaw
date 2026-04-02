from src.agents.common.base import BaseAgent
from src.agents.mainagent.context import MainContext


class MainAgent(BaseAgent):
    name="核心智能体"
    description = "具备规划、深度分析和子智能体协作能力的智能体，可以处理复杂的多步骤任务"
    context_schema =MainContext
    tools=[]

    def __init__(self,**kwargs):
        super().__init(**kwargs)
        self.graph=None
        self.checkpointer=None

    async def get_tools(self):
        pass
    async def get_graph(self,**kwargs):
        context=self.context_schema
