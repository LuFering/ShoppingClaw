"""数据库模型定义,使用 SQLAlchemy 进行 ORM（对象关系映射）建模"""
from typing import Any

from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean, UniqueConstraint, Index, Text, ForeignKey
from sqlalchemy.orm import declarative_base, relationship

from src.utils.datetime_utils import utc_now_naive, format_utc_datetime

# SQLAlchemy 是ORM（对象关系映射）框架，用于在 Python 代码和关系型数据库之间建立桥梁
# 所有继承自 Base 的类都会自动映射到数据库表
Base = declarative_base()
class OperationLog(Base):
    """操作日志模型"""

    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    operation = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=utc_now_naive)

    # 关联用户
    user = relationship("User", back_populates="operation_logs")

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "operation": self.operation,
            "details": self.details,
            "ip_address": self.ip_address,
            "timestamp": format_utc_datetime(self.timestamp),
        }

class User(Base):
    """用户模型表"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_name = Column(String, nullable=False, unique=True, index=True)  # 用户名称
    user_id = Column(String, nullable=False, unique=True, index=True)  # 登录ID
    phone_number = Column(String, nullable=False, unique=True, index=True)  # 手机号
    config_json=Column(JSON,nullable=True,default={})
    shipping_address=Column(String,nullable=False)
    avatar = Column(String, nullable=True)  # 头像URL
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False, default="user")  # 角色：superadmin,admin,user
    created_at = Column(DateTime, default=utc_now_naive)
    last_login = Column(DateTime, nullable=True)

    # 登录失败限制相关字段
    login_failed_count = Column(Integer, nullable=False, default=0)  # 登录失败次数
    last_failed_login = Column(DateTime, nullable=True)  # 最后一次登录失败时间
    login_locked_until = Column(DateTime, nullable=True)  # 锁定到什么时候

    # 软删除相关字段
    is_deleted = Column(Integer, nullable=False, default=0, index=True)  # 是否已删除：0=否，1=是
    deleted_at = Column(DateTime, nullable=True)  # 删除时间

    # 关联操作日志
    #operation_logs = relationship("OperationLog", back_populates="user", cascade="all,delete-orphan")

    def to_dict(self, include_password: bool = False) -> dict[str, Any]:
        result = {
            "id": self.id,
            "user_name": self.user_name,
            "user_id": self.user_id,
            "phone_number": self.phone_number,
            "avatar": self.avatar,
            "role": self.role,
            "created_at": format_utc_datetime(self.created_at),
            "last_login": format_utc_datetime(self.last_login),
            "login_failed_count": self.login_failed_count,
            "last_failed_login": format_utc_datetime(self.last_failed_login),
            "login_locked_until": format_utc_datetime(self.login_locked_until),
            "is_deleted": self.is_deleted,
            "deleted_at": format_utc_datetime(self.deleted_at),
        }
        if include_password:  # 一般情况不需要传password用于前端展示
            result["password_hash"] = self.password_hash
        return result

    def is_login_locked(self) -> bool:
        """检查用户是否处于登录锁定状态"""
        if self.login_locked_until is None:
            return False
        return utc_now_naive() < self.login_locked_until

    def get_remaining_lock_time(self) -> int:
        """获取剩余锁定时间（秒）"""
        if self.login_locked_until is None:
            return 0
        remaining = int((self.login_locked_until - utc_now_naive()).total_seconds())
        return max(0, remaining)

    def reset_failed_login(self):
        """重置登录失败相关字段"""
        self.login_failed_count = 0
        self.last_failed_login = None
        self.login_locked_until = None

class AgentConfig(Base):
    """智能体配置表"""
    __tablename__ = "agent_configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(64), nullable=False, index=True)

    name = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    icon = Column(String(255), nullable=True)
    pics = Column(JSON, nullable=False, default=list)
    examples = Column(JSON, nullable=False, default=list)
    config_json = Column(JSON, nullable=False, default=dict)

    is_default = Column(Boolean, nullable=False, default=False, index=True)

    created_by = Column(String(64), nullable=True)
    updated_by = Column(String(64), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "icon": self.icon,
            "pics": self.pics or [],
            "examples": self.examples or [],
            "config_json": self.config_json or {},
            "is_default": bool(self.is_default),
            "created_by": self.created_by,
            "updated_by": self.updated_by,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }

class KnowledgeFaq(Base):
    """FAQ高频问答表"""
    __tablename__ = "knowledge_faq"

    __table_args__ = (
        UniqueConstraint("doc_id", "question", name="uq_knowledge_faq_doc_question"),
        Index("ix_knowledge_faq_doc_active", "doc_id", "is_active"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    doc_id = Column(String(255), nullable=False, index=True)
    question = Column(String(500), nullable=False)
    answer = Column(String(4000), nullable=False)
    category = Column(String(100), nullable=True, index=True)
    tags = Column(JSON, default=list)
    question_keywords = Column(JSON, default=list)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

class KnowledgeRetrievalLog(Base):
    """检索日志表（用于质量监控）"""
    __tablename__ = "knowledge_retrieval_log"

    id = Column(Integer, primary_key=True, autoincrement=True)
    query = Column(String(500), nullable=False)
    category = Column(String(100), nullable=True)
    source_types = Column(JSON, default=list)
    result_count = Column(Integer, default=0)
    latency_ms = Column(Integer, default=0)
    is_hit = Column(Boolean, default=True)
    is_bad_case = Column(Boolean, default=False)
    bad_case_note = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, index=True)
