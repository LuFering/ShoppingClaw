from pathlib import Path
import yaml
from langchain.agents import create_agent
from langchain_core.prompts import ChatPromptTemplate
from src.agents.common.model import load_chat_model
from src.agents.common.toolkits import get_all_tool_instances

# 导入 SubAgent 输出协议
try:
    from agents.common.model import ResearcherOutput, AnalystOutput, CriticOutput, MemoryOutput
except ImportError:
    ResearcherOutput = AnalystOutput = CriticOutput = MemoryOutput = None


def _get_tool_by_name(tool_name: str):
    """从全局注册表查找工具"""
    all_tools = get_all_tool_instances()
    for tool in all_tools:
        if hasattr(tool, 'name') and tool.name == tool_name:
            return tool
    return None


def create_subagent_from_config(config_path: Path) -> list[dict]:
    """从 YAML 配置批量创建 ReAct 子智能体"""
    with open(config_path, encoding='utf-8') as f:
        config = yaml.safe_load(f)

    subagents = []
    for name, spec in config.items():
        # 1. 加载模型
        model_name = spec.get("model")
        print(f"[SubAgent Factory] 正在为 '{name}' 加载模型: {model_name}")
        model = load_chat_model(model_name)

        # 2. 解析工具
        tool_names = spec.get("tools", [])
        tools = [_get_tool_by_name(t) for t in tool_names if _get_tool_by_name(t)]

        # 3. 构建 Prompt
        prompt = ChatPromptTemplate.from_messages([
            ("system", spec.get("system_prompt", "")),
            ("placeholder", "{messages}"),
        ])

        # 4. 启用结构化输出 (如果定义了 Schema)
        structured_model = model
        schema_map = {
            "researcher": ResearcherOutput,
            "analyst": AnalystOutput,
            "critic": CriticOutput,
            "memory_manager": MemoryOutput
        }
        
        if name in schema_map and schema_map[name]:
            print(f"[SubAgent Factory] 为 '{name}' 启用 {schema_map[name].__name__} 结构化输出")
            structured_model = model.with_structured_output(schema_map[name])

        # 5. 创建 Agent（使用新版 create_agent）
        react_agent = create_agent(structured_model, tools, prompt)

        subagents.append({
            "name": name,
            "description": spec.get("description", ""),
            "runnable": react_agent,  # ← 关键：直接传编译好的 Runnable
        })

    return subagents
