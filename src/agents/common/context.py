from pydantic import BaseModel, Field
from typing import Optional, Dict, Any


class BaseContext(BaseModel):
    """Agent 上下文基类"""
    user_id: str = Field(default="", description="用户ID")
    thread_id: str = Field(default="", description="会话线程ID")
    department_id: Optional[str] = Field(default=None, description="部门ID")
    agent_config_id: Optional[int] = Field(default=None, description="Agent配置ID")
    agent_config: Dict[str, Any] = Field(default_factory=dict, description="Agent配置")
    
    class Config:
        extra = "allow"  # 允许额外字段