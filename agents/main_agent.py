"""
主 Agent - 协调各个子 Agent
"""
from deepagents.graph import create_main_agent
from dotenv import load_dotenv
import os
# from infra.agent_factory import get_agent


class MainAgent:
    """主 Agent 类"""

    def __init__(self) -> None:
        """初始化主 Agent"""
        self._memory = ["./AGENT.md"],
        self._skill = ["./skill"],
        self._tools = [],
        self._subagents = self.load_subagents(),
        self._backend = None,
        self._agent = self.create_agent()

    def create_agent(self):
        """agent创建逻辑"""
        return create_main_agent(
            memory=self._memory,
            skills=self._skill,
            tools=[],
            subagents=self.load_subagents(),
            backend=None,
        )

    def invoke(self, user_input: str):
        """agent代理调用"""
        return self._agent.invoke(user_input)

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

"""langsmith加载"""
load_dotenv()
api_key = os.getenv("LANGCHAIN_API_KEY")
print(api_key)

"""agent调试"""
if __name__ == "__main__":
    agent = MainAgent()
    agent.invoke("你好，帮我挑选一件手机")
