"""
主 Agent - 协调各个子 Agent
"""
from typing import Any

from dotenv import load_dotenv

from langchain_core.messages import HumanMessage
from src.agents.mainagent.agent_demo import create_main_agent

# ========== 配置日志过滤 ==========
import logging

# 设置根 logger 级别为 INFO（只显示 INFO 及以上）
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# 过滤掉第三方库的 DEBUG 日志
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("langsmith").setLevel(logging.WARNING)
logging.getLogger("langchain").setLevel(logging.WARNING)
logging.getLogger("langgraph").setLevel(logging.WARNING)

# 只保留 root logger 的 DEBUG（你的 logging.debug 使用的是 root logger）
logging.getLogger("root").setLevel(logging.DEBUG)


# ====================================


# from infra.agent_factory import get_agent


class MainAgent:
    """主 Agent 类"""

    def __init__(self, persistence: bool = False) -> None:
        """初始化主 Agent"""
        self._memory = ["./AGENT.md"],
        self._skill = ["./skill"],
        self._tools = [],
        self.persistence = persistence,
        self._subagents = self.load_subagents(),
        self._backend = None,
        self._agent = self.create_agent()

    def create_agent(self):
        """agent 创建逻辑"""
        config = {
            "model": "qwen2.5:3b",
        }
        if self.persistence:  # checkpointer 持久化
            from langgraph.checkpoint.memory import MemorySaver
            config["checkpointer"] = MemorySaver()
    
        return create_main_agent(**config)

    def invoke(self, user_input: str, thread_id: str = "default") -> dict[str, Any]:
        """agent代理调用"""

        messages = {
            "messages": [HumanMessage(content=user_input)]
        }

        logging.info("[WORKFLOW] >>> 开始执行(进入__start__节点)")
        logging.debug(f"[WORKFLOW] 输入数据:{repr(user_input)}")

        config = {"configurable": {"thread_id": thread_id}}

        result = self._agent.invoke(messages, config)  # type: ignore[arg-type]

        logging.info("[WORKFLOW] <<< 执行完成(到达__end__节点)")
        logging.debug(f"[WORKFLOW] 输出数据:{repr(result)}")

        return result

    def load_subagents(self):
        # TODO: 实现子代理加载
        pass

    async def process_request(self, user_input: str) -> dict[str, Any]:
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

"""agent调试"""
if __name__ == "__main__":
    agent = MainAgent()
    while True:
            user_input = input("你:").strip()
            agent.invoke(user_input, thread_id="user_1")
