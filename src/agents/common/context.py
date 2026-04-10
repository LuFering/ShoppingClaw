import logging
import os.path
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.config import config
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, Annotated, Self

from src.services.mcp_service import get_mcp_serve_names


@dataclass(kw_only=True) #dataclass自动注入构造函数等，kw_only规定必须传入关键词参数
class BaseContext:
    """
    定义一个基础 Context 供 各类 graph 继承

    配置优先级:
    1. 运行时配置(RunnableConfig)：最高优先级，直接从函数参数传入
    2. 文件配置(config.private.yaml)：中等优先级，从文件加载
    3. 类默认配置：最低优先级，类中定义的默认值
    """
    def update(self,data:dict):
        """更新配置字段"""
        for key,value in data.items():
            if hasattr(self,key):
                setattr(self,key,value)

    thread_id:str=field(
        default_factory=lambda :str(uuid.uuid4()),
        metadata={"name":"线程ID","configurable":False,"description":"用来唯一标识一个对话线程"},
    )

    user_id:str=field(
        default_factory=lambda :str(uuid.uuid4()),
        metadata={"name":"用户ID","configurable":False,"description":"用来唯一标识一个用户"},
    )

    system_prompt:str=field(
        default="You are a helpful assistant.",
        metadata={
            "__template_metadata__": {"kind": "prompt"},#提供给LangGraph Studio
            "name": "系统提示词",
            "description": "用来描述智能体的角色和行为"
        },
    )

    model:str=field(
        default=config.default_model,
        metadata={
            "__template_metadata__":{"kind":"llm"},
            "name":"智能体模型",
            "options":[],
            "description":"智能体的驱动模型，建议选择 Agent 能力较强的模型，不建议使用小参数模型",
        },
    )

    tools:list[dict]=field(
        default_factory=list,
        metadata={
            "__template_metadata__":{"kind":"tools"},
            "name":"工具",
            "description":"内置工具",
        },
    )

    mcps:list[str]=field(
        default_factory=list,
        metadata={
            "__template_metadata__":{"kind":"mcps"},
            "name":"MCP服务器",
            "options":lambda :get_mcp_serve_names(),
            "description":(
                "MCP服务器列表，建议使用支持 SSE 的 MCP 服务器，"
                "如果需要使用 uvx 或 npx 运行的服务器，也请在项目外部启动 MCP 服务器，并在项目中配置 MCP 服务器。"
            ),
        },
    )

    skills:list[str]=field(
        default_factory=list,
        metadata={
            "__template_metadata__":{"kind":"skills"},
            "name":"Skills",
            "description":(
                "可选技能列表（由超级管理员维护）。运行时仅挂载并只读暴露选中的skills,"
                "技能依赖的工具和 MCP 服务器也会被自动挂载。"
             ),
            "type":"list",
        },
    )

    @classmethod
    def from_file(cls,module_name:str,input_context:dict=None)->Self:
        """Load configuration from a YAML file. 用于持久化配置"""
        # 从文件加载配置
        context=cls()
        config_file_path=Path(config.save_dir)/"agents"/module_name/"config.yaml"
        if module_name is not None and os.path.exists(config_file_path):
            file_config={}
            try:
                with open(config_file_path,encoding="utf-8") as f:
                    file_config=yaml.safe_load(f) or {}
            except Exception as e:
                logging.error(f"加载智能体配置文件出错:{e}")

            context.update(file_config)

        return context





