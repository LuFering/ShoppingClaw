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
    """当前用户信息。

    ⚠️ 字段必须覆盖前端 `ProfileModal` 会显示的全部项 ——
    之前只回 5 个字段（id/username/role/created_at/last_login），
    而弹窗里还渲染了手机号与头像，于是那几行**永远是空的**，
    看起来像"资料没填"，实际是接口没给。

    没有 `email`：`users` 表里**根本没有这一列**。前端弹窗里那个「邮箱」
    行是照着别的项目套的模板，永远取不到值 —— 已在前端一并删掉，
    不在这里假装给它一个恒为 None 的字段。
    """
    id: int
    username: str
    user_id: str | None = None          # 登录 ID（与内部 id 不同）
    role: str
    phone_number: str | None = None
    avatar: str | None = None
    shipping_address: str | None = None
    created_at: str | None = None
    last_login: str | None = None


class ProfileUpdate(BaseModel):
    """可改的资料字段。全部可选 —— 只改传了的项。

    刻意**不允许**改 role / user_id：角色是权限字段，改它要走管理端；
    登录 ID 是身份标识，改了会让历史数据对不上。这两项即便传了也忽略。
    """
    username: str | None = None
    phone_number: str | None = None
    avatar: str | None = None
    shipping_address: str | None = None


class PasswordChange(BaseModel):
    """改密码必须验旧密码 —— 只带 token 就允许改，等于 token 泄露即可夺号。"""
    old_password: str
    new_password: str


class RegisterRequest(BaseModel):
    """注册。开放注册是有意为之（自用项目），但**只给 user 角色** ——
    不能通过注册接口拿到 admin。"""
    user_id: str
    username: str
    password: str
    phone_number: str | None = None


class InitializeRequest(BaseModel):
    """首次运行创建超级管理员。"""
    username: str
    password: str


user_repo = UserRepository()


def _to_user_response(u: DBUser) -> dict:
    """DBUser → 响应。统一一处，避免每个端点各拼一遍字段（漏一个就白屏一行）。"""
    d = u.to_dict()
    return {
        "id": d["id"],
        "username": d.get("user_name") or "",
        "user_id": d.get("user_id") or "",
        "role": d.get("role") or "user",
        "phone_number": d.get("phone_number"),
        "avatar": d.get("avatar"),
        "shipping_address": d.get("shipping_address"),
        "created_at": d.get("created_at"),
        "last_login": d.get("last_login"),
    }


# ── 路由：登录 ────────────────────────────────────────────

@auth.post("/token", response_model=Token)
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    """登录。**支持三种标识**：显示名 / 登录 ID / 手机号。

    登录表单上写的是「用户ID或手机号」，但原实现只查 `user_name`（显示名）——
    注册时用登录 ID 的用户**根本登不进来**（实测 401）。
    这里按「显示名 → 登录 ID → 手机号」依次找，第一个命中即用。
    """
    ident = (form_data.username or "").strip()
    user = (
        await user_repo.get_by_username(ident)
        or await user_repo.get_by_user_id(ident)
        or await user_repo.get_by_phone(ident)
    )
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
    """当前用户信息。字段形状见 `_to_user_response()`。"""
    return _to_user_response(current_user)


# ── 路由：注册 ────────────────────────────────────────────

@auth.post("/register", response_model=Token)
async def register(data: RegisterRequest):
    """注册新用户。

    两点刻意的约束：
      · **角色固定 user** —— 注册接口拿不到 admin，提权只能走管理端
      · `user_id` 与 `username` 都要唯一：前者是登录 ID，后者是显示名，
        历史上被当成同一个用过（initialize 里就写了两遍同一个值），
        新注册统一分开处理
    """
    if not re.match(r"^[a-zA-Z0-9_]+$", data.user_id):
        raise HTTPException(400, "登录 ID 只能包含字母、数字和下划线")
    if len(data.password) < 6:
        raise HTTPException(400, "密码至少 6 位")

    # ⚠️ 手机号可以不填，但**必须存 NULL 而不是空串**。
    # `phone_number` 上有一条唯一索引，而 Postgres 的唯一索引允许**多个 NULL**、
    # 却只允许**一个空串**。所以存 "" 的话：第一个没填手机号的用户能注册，
    # 第二个就撞 `ix_users_phone_number` 报 500（实测踩到，报的是
    # 「duplicate key value violates unique constraint」这种没法给用户看的话）。
    phone = (data.phone_number or "").strip() or None
    if phone and await user_repo.get_by_phone(phone):
        raise HTTPException(409, "该手机号已被使用")

    # ⚠️ 两个唯一约束查的是**不同的列**：
    #   get_by_username → user_name（显示名）
    #   get_by_user_id  → user_id  （登录 ID）
    # 之前这里用 get_by_username 去查登录 ID，查的是另一列 → 查不到 →
    # 走到 create 撞唯一约束 → 500。给调用方的应该是 409 + 一句人话。
    if await user_repo.get_by_user_id(data.user_id):
        raise HTTPException(409, "该登录 ID 已被占用")
    if await user_repo.get_by_username(data.username):
        raise HTTPException(409, "该用户名已被占用")

    user = await user_repo.create({
        "user_name": data.username,
        "user_id": data.user_id,
        "phone_number": phone,
        "password_hash": AuthUtils.hash_password(data.password),
        "role": "user",                      # ← 固定，不接受入参
        "shipping_address": "",
        "config_json": {},
    })

    token = AuthUtils.create_access_token({"sub": str(user.id)})
    return {
        "access_token": token,
        "token_type": "bearer",
        "user_id": user.id,
        "username": user.user_name,
        "user_id_login": user.user_id,
        "phone_number": user.phone_number,
        "avatar": user.avatar,
        "role": user.role,
    }


# ── 路由：改资料 ──────────────────────────────────────────

@auth.put("/me", response_model=UserResponse)
async def update_me(
    patch: ProfileUpdate,
    current_user: DBUser = Depends(get_required_user),
):
    """改个人资料。只改传了的字段。

    role / user_id 不在 ProfileUpdate 里 —— 传了也进不来（Pydantic 丢弃），
    这是刻意的：角色是权限字段，登录 ID 是身份标识。
    """
    updates: dict = {}

    if patch.username is not None:
        name = patch.username.strip()
        if not (3 <= len(name) <= 20):
            raise HTTPException(400, "用户名长度必须在 3-20 个字符之间")
        # 改成一个已被占用的名字要拦住（唯一约束会报 500，不如提前给准话）
        other = await user_repo.get_by_username(name)
        if other is not None and other.id != current_user.id:
            raise HTTPException(409, "该用户名已被占用")
        updates["user_name"] = name

    for f in ("phone_number", "avatar", "shipping_address"):
        v = getattr(patch, f)
        if v is not None:
            updates[f] = v

    if not updates:
        return _to_user_response(current_user)

    user = await user_repo.update(current_user.id, updates)
    if user is None:
        raise HTTPException(404, "用户不存在")
    return _to_user_response(user)


# ── 路由：改密码 ──────────────────────────────────────────

@auth.post("/password")
async def change_password(
    body: PasswordChange,
    current_user: DBUser = Depends(get_required_user),
):
    """改密码。**必须验旧密码** —— 只凭 token 就允许改，等于 token 泄露即可夺号。"""
    if not AuthUtils.verify_password(current_user.password_hash, body.old_password):
        raise HTTPException(400, "原密码不正确")
    if len(body.new_password) < 6:
        raise HTTPException(400, "新密码至少 6 位")
    if body.new_password == body.old_password:
        raise HTTPException(400, "新密码不能与原密码相同")

    await user_repo.update(current_user.id, {
        "password_hash": AuthUtils.hash_password(body.new_password),
        # 改完密码清掉失败计数与锁定 —— 否则之前被锁的号改完还是锁着
        "login_failed_count": 0,
        "login_locked_until": None,
    })
    return {"success": True}
