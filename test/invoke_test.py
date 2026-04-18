import asyncio

from src.agents import agent_manager
from src.storage.postgres.models_business import User


async def main():
    query=input("你：")
    # 构造匿名用户
    anonymous_user = User(
        user_name="anonymous",
        user_id="test-user",
        phone_number="00000000000",
        password_hash="dummy"
    )

    agent=agent_manager.get_agent("MasterAgent")

    input_context = {
        "user_id": anonymous_user.user_id,
        "thread_id": "test-thread-001",
    }
    # 调用 invoke_messages
    result = await agent.invoke_messages(
        messages=[query],
        input_context=input_context
    )
    print(result)

if __name__ == "__main__":
    asyncio.run(main())