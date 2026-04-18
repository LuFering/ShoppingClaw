import asyncio
import json
# 直接导入服务函数，绕过 FastAPI 路由和 Depends
from src.services.chat_stream_service import stream_agent_chat

from src.storage.postgres.models_business import User


async def main():
    query = input("你：")

    # 构造匿名用户
    anonymous_user = User(
        user_name="anonymous",
        user_id="test-user",
        phone_number="00000000000",
        password_hash="dummy"
    )

    # 直接调用流式服务
    response_stream = stream_agent_chat(
        agent_name="MasterAgent",
        query=query,
        config={"thread_id": "test-thread-001"},
        meta={"request_id": "test-req-001"},
        image_content=None,
        current_user=anonymous_user,
        db=None
    )

    # 遍历流式输出
    async for chunk in response_stream:
        # chunk 通常是 bytes 或 dict，根据实际情况打印
        print(chunk.decode('utf-8') if isinstance(chunk, bytes) else chunk)


if __name__ == "__main__":
    asyncio.run(main())
