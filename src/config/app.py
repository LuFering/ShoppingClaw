import os
from pathlib import Path

from pydantic import BaseModel, Field

from src.config.static.models import ChatModelProvider, DEFAULT_CHAT_MODEL_PROVIDERS


class Config(BaseModel):
    """应用配置类"""

    #基础配置
    save_dir: str = Field(default="saves", description="保存目录")
    model_dir: str = Field(default="", description="本地模型目录")

    #功能开关
    enable_reranker: bool = Field(default=False, description="是否开启重排序")
    enable_content_guard: bool = Field(default=False, description="是否启用内容审查")
    enable_content_guard_llm: bool = Field(default=False, description="是否启用LLM内容审查")
    enable_web_search: bool = Field(default=False, description="是否启用网络搜索")

    #模型配置
    default_model:str=Field(
        default="deepseek/deepseek-v4-flash",
        description="默认对话模型",
    )
    # 模型信息（只读，不持久化）
    model_name:dict[str,ChatModelProvider]=Field(
        default_factory=lambda :DEFAULT_CHAT_MODEL_PROVIDERS.copy(),
        description="聊天模型提供商配置",
        exclude=True,
    )
    def __init__(self,**data):
        super().__init__(**data)
        self._setup_paths()

    def _setup_paths(self):
        """设置配置文件路径"""
        self.save_dir=os.getenv("SAVE_DIR") or self.save_dir
        self._config_file=Path(self.save_dir)/"config"/"base.toml"
        self._config_file.parent.mkdir(parents=True,exist_ok=True)

config=Config()