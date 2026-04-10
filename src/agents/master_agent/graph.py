from pathlib import Path

import yaml
from langchain.agents.middleware import ToolCallLimitMiddleware, TodoListMiddleware

from src.agents.common.base import BaseAgent
from src.agents.common.middleware.filesystem import FilesystemMiddleware
from src.agents.common.middleware.patch_tool_calls import PatchToolCallsMiddleware
from src.agents.common.middleware.skills import SkillsMiddleware
from src.agents.common.middleware.subagents import SubAgentMiddleware
from src.agents.common.middleware.summarization import SummaryOffloadMiddleware
from src.agents.common.models import load_chat_model
from src.agents.common.toolkits import get_all_tool_instances
from src.agents.master_agent.context import MasterContext
from src.agents.master_agent.agent_demo import create_master_agent

# 导入硬编码工具模块，触发 @tool 装饰器的自动注册逻辑
import src.agents.common.toolkits.buildin.tools

def load_subagent(config_path:Path)->list:
    with open(config_path) as f:
        config=yaml.safe_load(f)
    subagents=[]
    for name,spec in config.items():
        subagent={
            "name":name,
            "description":spec["description"],
            "system_prompt":spec["system_prompt"],
        }
        if "model" in spec:
            subagent["model"]=spec["model"]
        if "tools" in spec:
            subagent["tools"]=spec["tools"]
        subagents.append(subagent)
    return subagents

class MasterAgent(BaseAgent):
    name="核心智能体"
    description = "具备规划、深度分析和子智能体协作能力的智能体，可以处理复杂的多步骤任务"
    context_schema =MasterContext
    capabilities=[]

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.graph=None
        self.checkpointer=None

    async def get_tools(self):
        """获取所有已注册的硬编码工具实例"""
        return get_all_tool_instances()
    
    async def get_graph(self, **kwargs):
        """获取或创建 Agent 图"""

        #获取上下文配置
        context=self.context_schema.from_file(module_name=self.module_name)

        model=load_chat_model(context.model)
        sub_model=load_chat_model(context.subagents_model)
        # tools=await self.get_tools()
        # subagents = load_subagent(Path(__file__).parent.parent / "subagents" / "subagents.yaml")
        #
        # # 主 Agent 上下文优化：90k tokens 触发压缩（128k context window 的 70%）
        # summary_middleware = SummaryOffloadMiddleware(
        #     model=model,
        #     trigger=("tokens", 90000),
        #     trim_tokens_to_summarize=4000,
        #     summary_offload_threshold=500,
        #     max_retention_ratio=0.5,
        # )
        # # 子 Agent 独立的上下文优化：更激进的压缩策略
        # sub_summary_middleware = SummaryOffloadMiddleware(
        #     model=sub_model,
        #     trigger=("tokens", 50000),
        #     trim_tokens_to_summarize=2000,
        #     summary_offload_threshold=300,
        #     max_retention_ratio=0.4,
        # )
        # subagents_middleware = SubAgentMiddleware(
        #     default_model=sub_model,
        #     default_tools=search_tools,
        #     subagents=subagents,
        #     default_middleware=[
        #         RuntimeConfigMiddleware(
        #             model_context_name="subagents_model",
        #             enable_model_override=True,
        #             enable_system_prompt_override=False,
        #             enable_tools_override=False,
        #         ),
        #         PatchToolCallsMiddleware(),
        #         sub_summary_middleware,
        #         # 子 Agent 搜索工具限制：tavily_search 最多 8 次
        #         ToolCallLimitMiddleware(
        #             tool_name="tavily_search",
        #             run_limit=8,
        #             exit_behavior="continue",
        #         ),
        #     ],
        #     general_purpose_agent=True,
        # )


        # 调用工厂函数创建 graph
        graph = create_master_agent(
            model=model,
            # tools=tools,
            # middleware=[
            #     FilesystemMiddleware(backend=_create_fs_backend),  # 文件系统后端
            #     RuntimeConfigMiddleware(extra_tools=all_mcp_tools),
            #     SkillsMiddleware(),  # Skills 中间件（提示词注入、依赖展开、动态激活）
            #     save_attachments_to_fs,  # 附件注入提示词
            #     TodoListMiddleware(),
            #     PatchToolCallsMiddleware(),
            #     subagents_middleware,
            #     summary_middleware,
            #     # 工具调用限制：tavily_search 总调用最多 20 次
            #     ToolCallLimitMiddleware(
            #         tool_name="tavily_search",
            #         thread_limit=20,
            #         exit_behavior="continue",
            #     ),
            #     # 总工具调用轮次限制：防止单次运行无限循环
            #     ToolCallLimitMiddleware(
            #         run_limit=50,
            #         exit_behavior="end",
            #     ),
            # ],
            # checkpointer=await self._get_checkpointer(),
        )
        
        return graph
