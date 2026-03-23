"""
配置文件管理
"""
import os
from pathlib import Path


class Config:
    """配置类"""
    
    # 项目根目录
    BASE_DIR = Path(__file__).parent.parent
    
    # LLM 配置
    LLM_API_KEY = os.getenv("LLM_API_KEY", "")
    LLM_MODEL = os.getenv("LLM_MODEL", "gpt-3.5-turbo")
    
    # 数据库配置
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./workspace/data.db")
    
    # 向量存储配置
    VECTOR_STORE_PATH = os.getenv("VECTOR_STORE_PATH", "./workspace/vectors")
    
    # 日志配置
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    
    @classmethod
    def get_config(cls, key: str, default=None):
        """
        获取配置项
        
        Args:
            key: 配置键
            default: 默认值
            
        Returns:
            配置值
        """
        return getattr(cls, key, default)
