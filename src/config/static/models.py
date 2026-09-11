

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
    "SenseNova":ChatModelProvider(
            name="SenseNova",
            url="https://www.sensenova.cn/",
            base_url="https://token.sensenova.cn/v1",
            default="sensenova-6.8-flash-lite",
            env="SENSENOVA_API_KEY",
            models=["sensenova-6.8-flash-lite","deepseek-v4-flash"],
    ),
    "OpenRouter":ChatModelProvider(
            name="OpenRouter",
            url="https://openrouter.ai",
            # base_url 只到 /v1：SDK 会自行追加 /chat/completions，
            # 写成 .../v1/chat/completions 会导致最终路径重复而 404
            base_url="https://openrouter.ai/api/v1",
            default="nvidia/nemotron-3-super-120b-a12b:free",
            env="OPENROUTER_API_KEY",
            # 字段名必须是 models（复数）；写成 model 会被 Pydantic 静默忽略，
            # 导致 models 落到默认空列表，前端该分组无任何模型可显示。
            #
            # 注意： :free 模型走 OpenRouter 的「免费共享池」，高峰期经常被上游
            # 限流并返回 429（upstream_provider_shared_pool）。故此处保留多个
            # 可用备选，便于前端切换；如长期不稳定建议充值后改用付费模型。
            models=[
                "nvidia/nemotron-3-super-120b-a12b:free",
                "dots-studio/dots-3-note-preview:free",
                "inclusionai/ling-3.0-flash-vl:free",
                "nex-agi/nex-n2.5-mini:free",
                "google/gemma-4-31b-it:free",
                "poolside/laguna-s-2.1:free",
            ],
    )
}

