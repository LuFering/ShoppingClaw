

from pydantic import BaseModel, Field


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

config=Config()