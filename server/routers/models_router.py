"""
模型配置 API 路由

提供 RESTful API 管理用户的模型配置。
"""
import logging
from typing import List

from fastapi import APIRouter, Body, Depends, HTTPException

from server.utils.auth_middleware import get_required_user
from server.utils.user_store import User

router = APIRouter(prefix="/models", tags=["models"])


@router.get("/", response_model=List[dict])
async def list_models(
    current_user: User = Depends(get_required_user),
):
    """
    列出用户的所有模型配置
    
    Returns:
        模型配置列表
    """
    from src.models.model_config import get_model_config_manager
    
    manager = get_model_config_manager()
    configs = await manager.list_configs(str(current_user.id))
    
    return [
        {
            "id": config.id,
            "name": config.name,
            "provider": config.provider,
            "model_name": config.model_name,
            "base_url": config.base_url,
            "context_window": config.context_window,
            "max_tokens": config.max_tokens,
            "is_default": config.is_default,
            "created_at": config.created_at.isoformat(),
            "updated_at": config.updated_at.isoformat(),
        }
        for config in configs
    ]


@router.post("/", response_model=dict)
async def create_model(
    model_data: dict = Body(...),
    current_user: User = Depends(get_required_user),
):
    """
    添加新的模型配置
    
    Request Body:
    ```json
    {
      "name": "My DeepSeek",
      "provider": "deepseek",
      "base_url": "https://api.deepseek.com/v1",
      "api_key": "sk-xxx",
      "model_name": "deepseek-chat",
      "context_window": 64000,
      "max_tokens": 8192
    }
    ```
    
    Returns:
        新创建的模型配置
    """
    from src.models.model_config import get_model_config_manager
    
    # 验证必填字段
    required_fields = ["name", "provider", "base_url", "api_key", "model_name"]
    for field in required_fields:
        if field not in model_data:
            raise HTTPException(status_code=400, detail=f"Missing required field: {field}")
    
    manager = get_model_config_manager()
    
    try:
        config = await manager.add_config(
            user_id=str(current_user.id),
            **model_data
        )
        
        return {
            "message": "Model config created successfully",
            "config": {
                "id": config.id,
                "name": config.name,
                "provider": config.provider,
                "model_name": config.model_name,
                "is_default": config.is_default,
            }
        }
    except Exception as e:
        logging.error(f"[ModelsAPI] Failed to create model config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.put("/{config_id}", response_model=dict)
async def update_model(
    config_id: str,
    model_data: dict = Body(...),
    current_user: User = Depends(get_required_user),
):
    """
    更新模型配置
    
    Request Body:
    ```json
    {
      "name": "Updated Name",
      "base_url": "https://new-url.com",
      "context_window": 128000
    }
    ```
    
    Returns:
        更新后的模型配置
    """
    from src.models.model_config import get_model_config_manager
    
    manager = get_model_config_manager()
    
    try:
        config = await manager.update_config(
            user_id=str(current_user.id),
            config_id=config_id,
            **model_data
        )
        
        return {
            "message": "Model config updated successfully",
            "config": {
                "id": config.id,
                "name": config.name,
                "provider": config.provider,
                "model_name": config.model_name,
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"[ModelsAPI] Failed to update model config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{config_id}", response_model=dict)
async def delete_model(
    config_id: str,
    current_user: User = Depends(get_required_user),
):
    """
    删除模型配置
    
    Returns:
        删除确认消息
    """
    from src.models.model_config import get_model_config_manager
    
    manager = get_model_config_manager()
    
    try:
        await manager.delete_config(
            user_id=str(current_user.id),
            config_id=config_id
        )
        
        return {
            "message": "Model config deleted successfully",
            "config_id": config_id,
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"[ModelsAPI] Failed to delete model config: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{config_id}/set-default", response_model=dict)
async def set_default_model(
    config_id: str,
    current_user: User = Depends(get_required_user),
):
    """
    设置默认模型
    
    Returns:
        新的默认配置
    """
    from src.models.model_config import get_model_config_manager
    
    manager = get_model_config_manager()
    
    try:
        config = await manager.set_default(
            user_id=str(current_user.id),
            config_id=config_id
        )
        
        return {
            "message": "Default model set successfully",
            "config": {
                "id": config.id,
                "name": config.name,
                "provider": config.provider,
                "model_name": config.model_name,
                "is_default": True,
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logging.error(f"[ModelsAPI] Failed to set default model: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/default", response_model=dict)
async def get_default_model(
    current_user: User = Depends(get_required_user),
):
    """
    获取用户的默认模型配置
    
    Returns:
        默认模型配置，如果没有则返回空对象
    """
    from src.models.model_config import get_model_config_manager
    
    manager = get_model_config_manager()
    config = await manager.get_default_config(str(current_user.id))
    
    if not config:
        return {
            "has_default": False,
            "message": "No default model configured",
        }
    
    return {
        "has_default": True,
        "config": {
            "id": config.id,
            "name": config.name,
            "provider": config.provider,
            "model_name": config.model_name,
            "base_url": config.base_url,
            "context_window": config.context_window,
            "max_tokens": config.max_tokens,
        }
    }
