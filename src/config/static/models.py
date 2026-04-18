

from pydantic import BaseModel, Field


class ChatModelProvider(BaseModel):
    """聊天模型提供商配置"""

    name: str = Field(..., description="提供商显示名称")
    url: str = Field(..., description="提供商文档或模型列表 URL")
    base_url: str = Field(..., description="API 基础 URL")
    default: str = Field(..., description="默认模型名称")
    env: str = Field(..., description="API Key 环境变量名")
    models: list[str] = Field(default_factory=list, description="支持的模型列表")
    custom: bool = Field(default=False, description="是否为自定义供应商")

# 默认聊天模型配置
DEFAULT_CHAT_MODEL_PROVIDERS:dict[str,ChatModelProvider]={
    "openai":ChatModelProvider(
        name="OpenAI",
        url="https://platform.openai.com/docs/models",
        base_url="https://api.openai.com/v1",
        default="gpt-5-mini",
        env="OPENAI_API_KEY",
        models=["gpt-5.2", "gpt-5-mini", "gpt-5.2-pro"],
    ),
    "deepseek": ChatModelProvider(
            name="DeepSeek",
            url="https://platform.deepseek.com/api-docs/zh-cn/pricing",
            base_url="https://api.deepseek.com/v1",
            default="deepseek-chat",
            env="DEEPSEEK_API_KEY",
            models=["deepseek-chat", "deepseek-reasoner"],
        ),
    "ollama":ChatModelProvider(
        name="Ollama",
        url="https://docs.ollama.com/",
        base_url="http://localhost:11434",
        default="qwen2.5:3b",
        env="",
        models=["gemma4:e2b","qwen2.5:3b"],
    ),
    "aliyun":ChatModelProvider(
            name="Aliyun",
            url="https://dashscope.aliyuncs.com/",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
            default="tongyi-xiaomi-analysis-flash",
            env="DASHSCOPE_API_KEY",
            models=["tongyi-xiaomi-analysis-flash", "qwen3-max-2026-01-23"],
        ),
}

