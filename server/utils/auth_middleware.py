"""认证中间件 — 基于 JSON 用户存储的轻量实现"""
import re

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError

from server.utils.auth_utils import AuthUtils
from server.utils.user_store import get_user_by_id, User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)

PUBLIC_PATHS = [
    r"^/api/auth/token$",
    r"^/api/auth/check-first-run$",
    r"^/api/auth/initialize$",
    r"^/api$",
    r"^/api/system/health$",
    r"^/api/system/info$",
    r"^/docs.*",
    r"^/redoc.*",
    r"^/openapi.json$",
]


async def get_current_user(token: str | None = Depends(oauth2_scheme)) -> User | None:
    if token is None:
        return None

    try:
        payload = AuthUtils.verify_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的凭证",
                headers={"WWW-Authenticate": "Bearer"},
            )
    except (JWTError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e) if isinstance(e, ValueError) else "无效的凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = get_user_by_id(int(user_id))
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


async def get_required_user(user: User | None = Depends(get_current_user)) -> User:
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="请登录后再访问",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return user


async def get_admin_user(current_user: User = Depends(get_required_user)) -> User:
    if current_user.role not in ["admin", "superadmin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


def is_public_path(path: str) -> bool:
    path = path.rstrip("/")
    for pattern in PUBLIC_PATHS:
        if re.match(pattern, path):
            return True
    return False
