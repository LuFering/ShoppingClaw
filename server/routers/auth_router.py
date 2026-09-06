"""认证路由 — PostgreSQL 版：登录 + 初始化 + 个人信息"""
import logging
import re

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from server.utils.auth_middleware import get_current_user, get_required_user
from server.utils.auth_utils import AuthUtils
from src.repositories.user_repository import UserRepository
from src.storage.postgres.models_business import User as DBUser
from src.utils.datetime_utils import utc_now_naive

auth = APIRouter(prefix="/auth", tags=["authentication"])


# ── 响应模型 ──────────────────────────────────────────────

class Token(BaseModel):
    access_token: str
    token_type: str
    user_id: int
    username: str
    user_id_login: str
    phone_number: str | None = None
    avatar: str | None = None
    role: str


class UserResponse(BaseModel):
    id: int
    username: str
    role: str
    created_at: str | None = None
    last_login: str | None = None


class InitializeRequest(BaseModel):
    username: str
    password: str


user_repo = UserRepository()


# ── 路由：登录 ────────────────────────────────────────────

@auth.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    user = await user_repo.get_by_username(form_data.username)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if user.is_login_locked():
        remaining = user.get_remaining_lock_time()
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=f"登录被锁定，请等待 {remaining} 秒后再试",
            headers={"WWW-Authenticate": "Bearer", "X-Lock-Remaining": str(remaining)},
        )

    if not AuthUtils.verify_password(user.password_hash, form_data.password):
        updates = {
            "login_failed_count": user.login_failed_count + 1,
            "last_failed_login": utc_now_naive(),
        }
        if user.login_failed_count + 1 >= 5:
            from datetime import timedelta
            updates["login_locked_until"] = utc_now_naive() + timedelta(minutes=15)
        
        await user_repo.update(user.id, updates)

        if user.login_failed_count + 1 >= 5:
            remaining = 900  # 15 minutes
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"由于多次登录失败，账户已被锁定 {remaining} 秒",
                headers={"WWW-Authenticate": "Bearer", "X-Lock-Remaining": str(remaining)},
            )

        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await user_repo.update(user.id, {
        "last_login": utc_now_naive(),
        "login_failed_count": 0,
        "last_failed_login": None,
        "login_locked_until": None,
    })

    token_data = {"sub": str(user.id)}
    access_token = AuthUtils.create_access_token(token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.user_name,
        "user_id_login": user.user_id,
        "phone_number": user.phone_number,
        "avatar": user.avatar,
        "role": user.role,
    }


# ── 路由：检查首次运行 ────────────────────────────────────

@auth.get("/check-first-run")
async def check_first_run_endpoint():
    has_users = await user_repo.exists_by_username("admin")
    return {"first_run": not has_users}


# ── 路由：初始化管理员 ────────────────────────────────────

@auth.post("/initialize", response_model=Token)
async def initialize_admin(admin_data: InitializeRequest):
    exists = await user_repo.exists_by_username(admin_data.username)
    if exists:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="系统已经初始化，无法再次创建初始管理员",
        )

    if not re.match(r"^[a-zA-Z0-9_]+$", admin_data.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名只能包含字母、数字和下划线",
        )

    if len(admin_data.username) < 3 or len(admin_data.username) > 20:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名长度必须在3-20个字符之间",
        )

    hashed = AuthUtils.hash_password(admin_data.password)
    user = await user_repo.create({
        "user_name": admin_data.username,
        "user_id": admin_data.username,
        "phone_number": "00000000000",
        "password_hash": hashed,
        "role": "superadmin",
        "shipping_address": "",
        "config_json": {},
    })

    token_data = {"sub": str(user.id)}
    access_token = AuthUtils.create_access_token(token_data)

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.user_name,
        "user_id_login": user.user_id,
        "phone_number": user.phone_number,
        "avatar": user.avatar,
        "role": user.role,
    }


# ── 路由：当前用户信息 ────────────────────────────────────

@auth.get("/me", response_model=UserResponse)
async def read_users_me(current_user: DBUser = Depends(get_required_user)):
    user_dict = current_user.to_dict()
    return {
        "id": user_dict["id"],
        "username": user_dict["user_name"],
        "role": user_dict["role"],
        "created_at": user_dict["created_at"],
        "last_login": user_dict["last_login"],
    }
