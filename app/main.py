"""
ShoppingClaw - Deep Agents Shopping Agent
主应用入口
"""
from fastapi import FastAPI

from src.utils.infra.agent_factory import get_agent

app = FastAPI(
    title="ShoppingClaw",
    description="Deep Agents Shopping Agent - 智能购物助手",
    version="1.0.0"
)


@app.get("/")
async def root():
    """根路径"""
    return {"message": "Welcome to ShoppingClaw API"}


async def chat(user_input:str):
    agent=get_agent()
    return await agent.process_request()