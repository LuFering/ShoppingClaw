"""轻量级 JSON 文件用户存储，替代 PostgreSQL 依赖"""
import json
import os
import threading
from datetime import datetime
from typing import Any

USERS_FILE = "saves/users.json"
_lock = threading.Lock()


class User:
    """轻量用户对象，兼容原 SQLAlchemy User 模型的常用属性"""

    def __init__(self, data: dict[str, Any]):
        self.id: int = data["id"]
        self.username: str = data["username"]
        self.password_hash: str = data["password_hash"]
        self.role: str = data.get("role", "user")
        self.created_at: str | None = data.get("created_at")
        self.last_login: str | None = data.get("last_login")
        self.login_failed_count: int = data.get("login_failed_count", 0)
        self.last_failed_login: str | None = data.get("last_failed_login")
        self.login_locked_until: str | None = data.get("login_locked_until")

    def to_dict(self, include_password: bool = False) -> dict[str, Any]:
        result = {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "created_at": self.created_at,
            "last_login": self.last_login,
        }
        if include_password:
            result["password_hash"] = self.password_hash
        return result

    def is_login_locked(self) -> bool:
        if self.login_locked_until is None:
            return False
        return datetime.now().isoformat() < self.login_locked_until

    def get_remaining_lock_time(self) -> int:
        if self.login_locked_until is None:
            return 0
        try:
            locked_until = datetime.fromisoformat(self.login_locked_until)
            remaining = int((locked_until - datetime.now()).total_seconds())
            return max(0, remaining)
        except ValueError:
            return 0

    def reset_failed_login(self):
        self.login_failed_count = 0
        self.last_failed_login = None
        self.login_locked_until = None

    def increment_failed_login(self):
        self.login_failed_count += 1
        self.last_failed_login = datetime.now().isoformat()
        if self.login_failed_count >= 5:
            from datetime import timedelta
            self.login_locked_until = (datetime.now() + timedelta(minutes=15)).isoformat()


def _load_users() -> list[dict]:
    if not os.path.exists(USERS_FILE):
        return []
    with open(USERS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_users(users: list[dict]):
    os.makedirs(os.path.dirname(USERS_FILE), exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, ensure_ascii=False, indent=2)


def check_first_run() -> bool:
    return not os.path.exists(USERS_FILE) or len(_load_users()) == 0


def get_user_by_id(user_id: int) -> User | None:
    users = _load_users()
    for u in users:
        if u["id"] == user_id:
            return User(u)
    return None


def get_user_by_username(username: str) -> User | None:
    users = _load_users()
    for u in users:
        if u["username"] == username:
            return User(u)
    return None


def create_user(username: str, password_hash: str, role: str = "user") -> User:
    with _lock:
        users = _load_users()
        new_id = max([u["id"] for u in users], default=0) + 1
        now = datetime.now().isoformat()
        user_data = {
            "id": new_id,
            "username": username,
            "password_hash": password_hash,
            "role": role,
            "created_at": now,
            "last_login": None,
            "login_failed_count": 0,
            "last_failed_login": None,
            "login_locked_until": None,
        }
        users.append(user_data)
        _save_users(users)
    return User(user_data)


def init_first_admin(username: str, password_hash: str) -> User:
    if not check_first_run():
        raise RuntimeError("System already initialized")
    return create_user(username, password_hash, role="superadmin")


def update_user(user_id: int, updates: dict[str, Any]):
    with _lock:
        users = _load_users()
        for u in users:
            if u["id"] == user_id:
                u.update(updates)
                break
        _save_users(users)
