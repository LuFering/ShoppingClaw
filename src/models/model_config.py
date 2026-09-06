"""
模型配置管理 - 参考 ScienceClaw 的 ModelConfig

允许用户动态管理多个模型配置，支持运行时切换。
"""
import logging
from src.utils.loop_safe_lock import loop_safe
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """
    用户模型配置
    
    字段说明:
    - id: 唯一标识符（自动生成）
    - user_id: 所属用户 ID
    - name: 用户可见名称（如 "DeepSeek V4"）
    - provider: 提供商类型（deepseek / openai / ollama / aliyun）
    - base_url: API 基础 URL
    - api_key: API Key（加密存储）
    - model_name: 实际模型名（如 "deepseek-v4-flash"）
    - context_window: 上下文窗口大小（token 数）
    - max_tokens: 最大输出 token 数
    - is_default: 是否为默认模型
    - created_at: 创建时间
    - updated_at: 更新时间
    """
    
    id: str = Field(
        default_factory=lambda: uuid.uuid4().hex[:12],
        description="配置 ID"
    )
    user_id: str = Field(..., description="用户 ID")
    name: str = Field(..., description="显示名称", min_length=1, max_length=50)
    provider: str = Field(
        ...,
        description="提供商类型",
        pattern="^(deepseek|openai|ollama|aliyun|custom)$"
    )
    base_url: str = Field(..., description="API 基础 URL")
    api_key: str = Field(..., description="API Key", min_length=1)
    model_name: str = Field(..., description="模型名称", min_length=1)
    context_window: int = Field(
        default=64000,
        description="上下文窗口大小",
        ge=1024,
        le=1000000
    )
    max_tokens: int = Field(
        default=8192,
        description="最大输出 token 数",
        ge=1,
        le=100000
    )
    is_default: bool = Field(default=False, description="是否为默认模型")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def to_provider_config(self) -> Dict[str, Any]:
        """
        转换为 ChatModelProvider 格式
        
        Returns:
            符合 ChatModelProvider 结构的字典
        """
        return {
            "name": self.name,
            "url": f"{self.base_url}/docs",
            "base_url": self.base_url,
            "default": self.model_name,
            "env": "",  # 用户配置不使用环境变量
            "models": [self.model_name],
            "custom": True,
        }
    
    def update_timestamp(self):
        """更新修改时间"""
        self.updated_at = datetime.utcnow()


class ModelConfigManager:
    """
    模型配置管理器
    
    功能:
    1. 管理用户的模型配置列表
    2. 支持增删改查操作
    3. 设置默认模型
    4. 持久化到文件系统
    
    使用方式:
    ```python
    manager = ModelConfigManager()
    
    # 添加模型配置
    config = await manager.add_config(
        user_id="user123",
        name="My DeepSeek",
        provider="deepseek",
        base_url="https://api.deepseek.com/v1",
        api_key="sk-xxx",
        model_name="deepseek-chat"
    )
    
    # 获取用户所有配置
    configs = await manager.list_configs(user_id="user123")
    
    # 设置默认模型
    await manager.set_default(user_id="user123", config_id=config.id)
    ```
    """
    
    def __init__(self, base_dir: str = "saves/models"):
        """
        初始化配置管理器
        
        Args:
            base_dir: 配置文件根目录
        """
        self.base_dir = Path(base_dir)
        self._configs: Dict[str, Dict[str, ModelConfig]] = {}
        self._lock = asyncio.Lock()
        
        # 加载已有配置
        self._load_all_configs()
    
    async def add_config(self, **kwargs) -> ModelConfig:
        """
        添加模型配置
        
        Args:
            **kwargs: ModelConfig 的参数字典
            
        Returns:
            新创建的 ModelConfig 实例
        """
        config = ModelConfig(**kwargs)
        user_id = config.user_id
        
        async with loop_safe(self._lock):
            if user_id not in self._configs:
                self._configs[user_id] = {}
            
            # 如果是第一个配置，自动设为默认
            if not self._configs[user_id]:
                config.is_default = True
            
            self._configs[user_id][config.id] = config
        
        # 持久化
        await self._save_user_configs(user_id)
        
        logging.info(f"[ModelConfigManager] Added config: {config.name} ({config.id})")
        return config
    
    async def list_configs(self, user_id: str) -> List[ModelConfig]:
        """
        列出用户的所有模型配置
        
        Args:
            user_id: 用户 ID
            
        Returns:
            ModelConfig 列表（按创建时间倒序）
        """
        async with loop_safe(self._lock):
            configs = self._configs.get(user_id, {})
        
        return sorted(
            configs.values(),
            key=lambda c: c.created_at,
            reverse=True
        )
    
    async def get_config(self, user_id: str, config_id: str) -> Optional[ModelConfig]:
        """
        获取单个模型配置
        
        Args:
            user_id: 用户 ID
            config_id: 配置 ID
            
        Returns:
            ModelConfig 实例或 None
        """
        async with loop_safe(self._lock):
            return self._configs.get(user_id, {}).get(config_id)
    
    async def update_config(self, user_id: str, config_id: str, **updates) -> ModelConfig:
        """
        更新模型配置
        
        Args:
            user_id: 用户 ID
            config_id: 配置 ID
            **updates: 要更新的字段
            
        Returns:
            更新后的 ModelConfig 实例
            
        Raises:
            ValueError: 配置不存在
        """
        async with loop_safe(self._lock):
            config = self._configs.get(user_id, {}).get(config_id)
            if not config:
                raise ValueError(f"Config not found: {config_id}")
            
            # 不允许直接修改 is_default（使用 set_default 方法）
            if "is_default" in updates:
                del updates["is_default"]
            
            # 更新字段
            for key, value in updates.items():
                if hasattr(config, key):
                    setattr(config, key, value)
            
            config.update_timestamp()
        
        # 持久化
        await self._save_user_configs(user_id)
        
        logging.info(f"[ModelConfigManager] Updated config: {config_id}")
        return config
    
    async def delete_config(self, user_id: str, config_id: str):
        """
        删除模型配置
        
        Args:
            user_id: 用户 ID
            config_id: 配置 ID
            
        Raises:
            ValueError: 配置不存在或是最后一个配置
        """
        async with loop_safe(self._lock):
            user_configs = self._configs.get(user_id, {})
            
            if config_id not in user_configs:
                raise ValueError(f"Config not found: {config_id}")
            
            # 不允许删除最后一个配置
            if len(user_configs) == 1:
                raise ValueError("Cannot delete the last config")
            
            deleted_config = user_configs.pop(config_id)
            
            # 如果删除的是默认配置，选择新的默认
            if deleted_config.is_default and user_configs:
                new_default = next(iter(user_configs.values()))
                new_default.is_default = True
        
        # 持久化
        await self._save_user_configs(user_id)
        
        logging.info(f"[ModelConfigManager] Deleted config: {config_id}")
    
    async def set_default(self, user_id: str, config_id: str) -> ModelConfig:
        """
        设置默认模型
        
        Args:
            user_id: 用户 ID
            config_id: 配置 ID
            
        Returns:
            新的默认配置
            
        Raises:
            ValueError: 配置不存在
        """
        async with loop_safe(self._lock):
            user_configs = self._configs.get(user_id, {})
            
            if config_id not in user_configs:
                raise ValueError(f"Config not found: {config_id}")
            
            # 取消其他配置的默认标记
            for config in user_configs.values():
                config.is_default = False
            
            # 设置新的默认配置
            new_default = user_configs[config_id]
            new_default.is_default = True
            new_default.update_timestamp()
        
        # 持久化
        await self._save_user_configs(user_id)
        
        logging.info(f"[ModelConfigManager] Set default config: {config_id}")
        return new_default
    
    async def get_default_config(self, user_id: str) -> Optional[ModelConfig]:
        """
        获取用户的默认模型配置
        
        Args:
            user_id: 用户 ID
            
        Returns:
            默认的 ModelConfig 或 None
        """
        async with loop_safe(self._lock):
            user_configs = self._configs.get(user_id, {})
        
        for config in user_configs.values():
            if config.is_default:
                return config
        
        # 如果没有默认配置，返回第一个
        if user_configs:
            return next(iter(user_configs.values()))
        
        return None
    
    def _load_all_configs(self):
        """从文件系统加载所有用户的配置"""
        if not self.base_dir.exists():
            return
        
        for user_dir in self.base_dir.iterdir():
            if not user_dir.is_dir():
                continue
            
            user_id = user_dir.name
            config_file = user_dir / "models.json"
            
            if not config_file.exists():
                continue
            
            try:
                import json
                data = json.loads(config_file.read_text(encoding="utf-8"))
                
                self._configs[user_id] = {
                    cid: ModelConfig(**cdata)
                    for cid, cdata in data.items()
                }
                
                logging.info(
                    f"[ModelConfigManager] Loaded {len(data)} configs for user {user_id}"
                )
            except Exception as e:
                logging.error(f"[ModelConfigManager] Failed to load configs for {user_id}: {e}")
    
    async def _save_user_configs(self, user_id: str):
        """保存用户的配置到文件系统"""
        import json
        
        user_dir = self.base_dir / user_id
        user_dir.mkdir(parents=True, exist_ok=True)
        
        config_file = user_dir / "models.json"
        
        async with loop_safe(self._lock):
            user_configs = self._configs.get(user_id, {})
            
            data = {
                cid: config.dict()
                for cid, config in user_configs.items()
            }
        
        config_file.write_text(
            json.dumps(data, indent=2, ensure_ascii=False, default=str),
            encoding="utf-8"
        )


# 全局单例
_model_config_manager: ModelConfigManager | None = None


def get_model_config_manager() -> ModelConfigManager:
    """获取全局 ModelConfigManager 实例"""
    global _model_config_manager
    if _model_config_manager is None:
        from pathlib import Path
        _model_config_manager = ModelConfigManager()
    return _model_config_manager
