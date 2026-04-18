from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError

from server.utils.auth_utils import AuthUtils
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import User

# 定义OAuth2密码承载器，指定token URL
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token", auto_error=False)


async def get_db():
    async with pg_manager.get_async_session_context() as db:
        yield db

# TODO:使用 Pydantic 模型作为 DTO,与 SQLAlchemy 模型解耦
# 获取当前用户（异步版本）
async def get_current_user(
        token: str | None = Depends(oauth2_scheme),  # ← 从请求头提取 token
        db: AsyncSession = Depends(get_db)  # ← 数据库会话
):
    credentials_exception = HTTPException(  # 创建一个标准的 HTTP 401 错误响应对象
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无效的凭证",
        headers={"WWW-Authenticate": "Bearer"}
    )

    # 允许无token访问公开路径
    if token is None:
        return None

    try:
        # 验证token
        payload = AuthUtils.verify_access_token(token)
        user_id = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    except ValueError as e:
        # 捕获AuthUtils.verify_access_token可能抛出的ValueError
        # 例如令牌过期或无效
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),  # 将错误信息直接传递给客户端
            headers={"WWW-Authenticate": "Bearer"},
        )

    # 查找用户（异步版本）
    from sqlalchemy import select
    result = await db.execute(select(User).filter(User.id == int(user_id)))
    user=result.scalar_one_or_none()
    if user is None:
        raise credentials_exception

    return user


async def get_required_user(user: User | None = Depends(get_current_user)):
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Not authenticated"
        )
    return user
