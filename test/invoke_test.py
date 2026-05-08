import asyncio
import sys
import logging

# 配置日志：确保能看到 INFO 级别的日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(name)s: %(message)s')

# 强制清除模块缓存，确保加载最新代码
for module_name in list(sys.modules.keys()):
    if 'src.agents' in module_name or 'factory' in module_name:
        del sys.modules[module_name]

from src.agents import agent_manager
from src.storage.postgres.models_business import User


async def main():
    query = input("你：")
    anonymous_user = User(
        user_name="anonymous",
        user_id="test-user",
        phone_number="00000000000",
        password_hash="dummy"
    )

    agent = agent_manager.get_agent("MasterAgent")
    input_context = {
        "user_id": anonymous_user.user_id,
        "thread_id": "test-thread-001",
    }
    
    print("\n--- Agent 回复开始 ---")

    async for msg, metadata in agent.stream_messages(
        messages=[query],
        input_context=input_context
    ):
        if hasattr(msg, 'content') and msg.content:
            print(msg.content, end="", flush=True)

    print("\n--- Agent 回复结束 ---")

if __name__ == "__main__":
    asyncio.run(main())