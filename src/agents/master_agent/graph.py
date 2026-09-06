from pathlib import Path

import yaml
from langchain.agents.middleware import ToolCallLimitMiddleware, TodoListMiddleware
from langgraph.checkpoint.memory import MemorySaver

from src.agents.common.base import BaseAgent
from src.agents.common.backends import StateBackend
from src.agents.common.middleware.filesystem import FilesystemMiddleware
# from src.agents.common.middleware.intent_detector import IntentDetectorMiddleware  # 暂时禁用
from src.agents.common.middleware.patch_tool_calls import PatchToolCallsMiddleware
# from src.agents.common.middleware.evidence_collector import EvidenceCollectorMiddleware  # 暂时禁用
# from src.agents.common.middleware.gap_detector import GapDetectorMiddleware  # 暂时禁用
from src.agents.common.middleware.skills import SkillsMiddleware
from src.agents.common.middleware.subagents import SubAgentMiddleware
from src.agents.common.middleware.summarization import SummaryOffloadMiddleware
from src.agents.common.models import load_chat_model
from src.agents.common.toolkits import get_all_tool_instances
from src.agents.common.toolkits.runtime import configure_runtime, get_lifecycle_handler
from src.agents.master_agent.context import MasterContext

# 工具模块延迟加载：由 toolkits.__init__ 的 _ensure_tools_loaded() 统一管理
# 避免服务启动时引入 sqlalchemy / knowledge_manager / jd / torch 等重量级依赖

def _get_tool_by_name(tool_name: str):
    """根据名称从全局注册表中查找工具实例"""
    all_tools = get_all_tool_instances()
    for tool in all_tools:
        if hasattr(tool, 'name') and tool.name == tool_name:
            return tool
    return None

def load_subagent(config_path:Path, default_model)->list:
    """从 YAML 加载子智能体配置并映射工具（支持 YAML 自定义模型）"""
    import logging
    with open(config_path, encoding='utf-8') as f:
        config=yaml.safe_load(f)
    subagents=[]
    for name,spec in config.items():
        # 1. 解析工具列表
        tool_names = spec.get("tools", [])
        resolved_tools = []
        for t_name in tool_names:
            tool_obj = _get_tool_by_name(t_name)
            if tool_obj:
                resolved_tools.append(tool_obj)
            else:
                print(f"Warning: Tool '{t_name}' not found for subagent '{name}'")
        
        # 2. 确定模型：优先使用 YAML 配置，如果没有则使用 default_model
        model_name = spec.get("model")

        if model_name:
            # logging.info(f"[SubAgent] {name} 正在加载 YAML 指定模型: {model_name}")
            agent_model = load_chat_model(model_name)
            # logging.info(f"[SubAgent] {name} 模型加载完成")
        else:
            # logging.info(f"[SubAgent] {name} 使用默认模型 (由 context.subagents_model 加载)")
            agent_model = default_model

        subagent={
            "name":name,
            "description":spec.get("description", ""),
            "system_prompt":spec.get("system_prompt", ""),
            "tools": resolved_tools,  # 3. 注入真正的工具对象
            "model": agent_model,     # 4. 注入确定的模型实例
        }
        subagents.append(subagent)
    return subagents

def _create_fs_backend(runtime):
    """为 FilesystemMiddleware 创建 StateBackend 实例"""
    return StateBackend(runtime)

class MasterAgent(BaseAgent):
    name="核心智能体"
    description = "具备规划、深度分析和子智能体协作能力的智能体，可以处理复杂的多步骤任务"
    context_schema =MasterContext
    capabilities=[]

    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.graph=None
        self.checkpointer=None
        self.sse_middleware=None  # SSEMonitoringMiddleware 实例，供 chat_stream_service 访问

    async def get_tools(self):
        """获取所有已注册的硬编码工具实例（buildin + MCP 工具）"""
        from src.agents.common.toolkits.registry import get_all_extra_metadata, ToolExtraMetadata
        import logging
        _logger = logging.getLogger(__name__)

        all_tools = get_all_tool_instances()
        extra_meta = get_all_extra_metadata()

        # 已由 Prompt 注入替代的工具（不应作为 Tool 暴露给 LLM）
        _deprecated_tool_names = {"ask_user_question"}

        # 只保留 buildin 类别的工具，并排除已弃用的工具
        tools = [
            tool for tool in all_tools
            if extra_meta.get(tool.name, ToolExtraMetadata()).category == "buildin"
            and tool.name not in _deprecated_tool_names
        ]

        # ── 加载 MCP 工具（本地 + 远程）──
        try:
            from src.services.mcp_service import get_tools_from_all_servers
            from src.services.mcp_tool_adapter import adapt_mcp_tools

            mcp_specs = await get_tools_from_all_servers()
            if mcp_specs:
                mcp_tools = await adapt_mcp_tools(mcp_specs)
                tools.extend(mcp_tools)
                _logger.info(f"[Agent] 加载了 {len(mcp_tools)} 个 MCP 工具: "
                             f"{[t.name for t in mcp_tools]}")
        except Exception as exc:
            _logger.warning(f"[Agent] MCP 工具加载失败（不影响核心功能）: {exc}")

        return tools

    async def _get_checkpointer(self):
        """获取检查点器（PostgreSQL 持久化）"""
        if self.checkpointer is None:
            # ═══ 使用 PostgreSQL Checkpointer（生产环境）═══
            from src.config import config as conf
            from src.agents.common.backends.postgres_checkpointer import get_postgres_checkpointer
            
            try:
                # 直接从环境变量获取 PostgreSQL 连接字符串
                import os
                db_url = os.getenv('POSTGRES_URL') or os.getenv('DATABASE_URL')
                
                # LangGraph Checkpointer 需要纯 PostgreSQL 格式，不是 SQLAlchemy 格式
                if db_url and db_url.startswith('postgresql+asyncpg://'):
                    db_url = db_url.replace('postgresql+asyncpg://', 'postgresql://')
                elif db_url and db_url.startswith('postgresql+psycopg://'):
                    db_url = db_url.replace('postgresql+psycopg://', 'postgresql://')
                
                if not db_url:
                    #  fallback 到手动拼接
                    db_user = os.getenv('POSTGRES_USER', 'postgres')
                    db_password = os.getenv('POSTGRES_PASSWORD', 'postgres')
                    db_host = os.getenv('POSTGRES_HOST', 'postgres')  # Docker 内使用服务名
                    db_port = os.getenv('POSTGRES_PORT', '5432')
                    db_name = os.getenv('POSTGRES_DB', 'shoppingclaw')
                    db_url = f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
                
                checkpointer_backend = get_postgres_checkpointer(db_url)
                self.checkpointer = await checkpointer_backend.get_checkpointer()
                
                import logging
                logging.info("[MasterAgent] ✅ Using PostgreSQL Checkpointer")
                
            except Exception as e:
                # ═══ Fallback: 使用 MemorySaver（开发环境或数据库不可用时）═══
                from langgraph.checkpoint.memory import MemorySaver
                import logging
                logging.warning(f"[MasterAgent] ⚠️ PostgreSQL Checkpointer failed, using MemorySaver: {e}")
                self.checkpointer = MemorySaver()
        
        return self.checkpointer
    
    async def get_graph(self, **kwargs):
        """获取或创建 Agent 图"""
        if self.graph is not None:
            return self.graph

        # 1. 获取上下文配置
        context=self.context_schema.from_file(module_name=self.module_name)

        # 2. 初始化模型
        model=load_chat_model(context.model)
        sub_model=load_chat_model(context.subagents_model)
        
        # 3. 获取工具与子智能体
        tools=await self.get_tools()
        subagents = load_subagent(Path(__file__).parent.parent / "subagents" / "subagents.yaml", sub_model)
        #
        # # 4. 配置中间件 (Middleware)
        #
        # # A. 摘要压缩：防止上下文溢出 (90k tokens 触发)
        # summary_middleware = SummaryOffloadMiddleware(
        #     model=model,
        #     trigger=("tokens", 90000),
        #     trim_tokens_to_summarize=4000,
        #     summary_offload_threshold=500,
        #     max_retention_ratio=0.5,
        # )
        #
        # # B. 子智能体管理：MasterAgent 的核心调度器
        subagents_middleware = SubAgentMiddleware(
            default_model=sub_model,
            default_tools=[],  # 子智能体默认不继承主智能体的工具，保持纯净
            subagents=subagents,
            default_middleware=[
                PatchToolCallsMiddleware(),
                SummaryOffloadMiddleware(
                    model=sub_model,
                    trigger=("tokens", 50000), 
                    trim_tokens_to_summarize=2000,
                ),
            ],
            general_purpose_agent=True,
        )

        # 5. 组装 Graph
        import logging
        from src.agents.common.middleware.content_guard import ContentGuardMiddleware
        from src.agents.common.middleware.offload import ToolResultOffloadMiddleware
        from src.agents.common.middleware.sse_monitor import SSEMonitoringMiddleware
        # from src.agents.common.middleware.state_injector import StateInjectorMiddleware  
        from src.agents.common.middleware.thinkingprocess import ThinkingProcessMiddleware
        from src.agents.master_agent.agent_demo import create_master_agent
        # logging.info("[MasterAgent] 正在编译 LangGraph...")
        
        # 创建状态后端（用于工具结果卸载）
        from src.agents.common.backends import FilesystemBackend
        state_backend = FilesystemBackend(root_dir="saves/state")

        # ═══ 初始化 ToolRuntime（六层框架的执行层 + 生命周期层）═══
        runtime = configure_runtime()
        logging.info("[GRAPH-DEBUG] ToolRuntime configured with Handler Chain")

        # ═══ 创建 SSE 监控中间件（保存引用供 chat_stream_service 获取事件）═══
        sse_monitor = SSEMonitoringMiddleware()
        self.sse_middleware = sse_monitor
        logging.info("[GRAPH-DEBUG] SSEMonitoringMiddleware created and registered")

        # ═══ 将 SSE 监控注册为生命周期事件消费者 ═══
        lifecycle_handler = get_lifecycle_handler()
        if lifecycle_handler:

            def _sse_sink(event_type: str, payload: dict) -> None:
                """将 Runtime 生命周期事件转发给 SSEMonitor。"""
                sse_monitor._emit({
                    "type": event_type,
                    "tool_name": payload.get("tool_name", ""),
                    "tool_call_id": payload.get("tool_call_id", ""),
                    "arguments": payload.get("args", {}),
                    "duration_ms": payload.get("duration_ms"),
                    "error": payload.get("error"),
                    "event_id": f"runtime_{event_type}",
                    "timestamp": payload.get("timestamp"),
                })

            lifecycle_handler.add_sink(_sse_sink)
            logging.info("[GRAPH-DEBUG] Runtime LifecycleHandler → SSEMonitor sink registered")

        graph = create_master_agent(
            model=model,
            context_schema=MasterContext,  # ← 传入 Context Schema 类
            tools=tools,
            middleware=[
                # ═══ 第一层：监控与安全 ═══
                sse_monitor,                         # 1. 工具调用监控（最外层，捕获所有调用）
                ContentGuardMiddleware(strict_mode=False),  # 2. 内容安全审查
                
                # ═══ 第二层：意图与规划 ═══
                #IntentDetectorMiddleware(),          # 3. 意图检测
                PatchToolCallsMiddleware(),          # 4. 修复工具调用格式
                
                # ═══ 第三层：证据收集与缺口检测 ═══
                #GapDetectorMiddleware(),             # 5. 检测证据缺口
                #EvidenceCollectorMiddleware(),       # 6. 结构化 SubAgent 输出
                #StateInjectorMiddleware(),           # 7. 将 state 注入 LLM 可见上下文
                
                # ═══ 第四层：工具执行控制 ═══
                ToolResultOffloadMiddleware(state_backend),  # 8. 大型结果卸载
                ToolCallLimitMiddleware(run_limit=10, thread_limit=20, exit_behavior="end"),  # 9. 调用次数限制
                TodoListMiddleware(),                # 10. 任务拆解

                # ═══ 第五层：文件系统与子智能体 ═══
                FilesystemMiddleware(backend=_create_fs_backend),  # 11. 文件读写能力
                subagents_middleware,                # 12. 子智能体调度

                # ═══ 第六层：后处理 ═══
                ThinkingProcessMiddleware(),         # 13. 思考过程提取
                # summary_middleware,                # 13. 长对话压缩（暂时禁用）
            ],
            checkpointer=await self._get_checkpointer(),
            # interrupt_after=["tools"],  # 已移除：工具执行后不应全局中断，应由具体工具内部调用 interrupt()
        )
        # logging.info("[MasterAgent] LangGraph 编译完成")
        self.graph = graph
        return self.graph
