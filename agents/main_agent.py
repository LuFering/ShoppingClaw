"""
主 Agent - 协调各个子 Agent
"""
from deepagents.graph import create_main_agent


class MainAgent:
    """主 Agent 类"""

    def __init__(self) -> None:
        """初始化主 Agent"""
        self._memory = ["./AGENT.md"],
        self._skill = ["./skill"],
        self._tools = [] ,
        self._subagents = self.load_subagents(),
        self._backend= None,
        self._agent=self.create_agent()

    def create_agent(self):
        return create_main_agent(
            memory=self._memory,
            skills=self._skill,
            tools=[],
            subagent=self.load_subagents(),
            backend=None,
        )

    def load_subagents(self):
        # TODO: 实现子代理加载
        pass

    async def process_request(self, user_input: str) -> dict:
        """
        处理用户请求
        
        Args:
            user_input: 用户输入
            
        Returns:
            处理结果
        """
        # TODO: 实现请求处理逻辑
        pass
