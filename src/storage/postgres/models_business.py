"""数据库模型定义,使用 SQLAlchemy 进行 ORM（对象关系映射）建模"""
from typing import Any

from sqlalchemy import Column, Integer, String, DateTime, JSON, Boolean, UniqueConstraint, Index, Text, ForeignKey
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import declarative_base, relationship

from src.utils.datetime_utils import utc_now_naive, format_utc_datetime

# SQLAlchemy 是ORM（对象关系映射）框架，用于在 Python 代码和关系型数据库之间建立桥梁
# 所有继承自 Base 的类都会自动映射到数据库表
Base = declarative_base()
class OperationLog(Base):
    """操作日志模型"""

    __tablename__ = "operation_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    operation = Column(String, nullable=False)
    details = Column(Text, nullable=True)
    ip_address = Column(String, nullable=True)
    timestamp = Column(DateTime, default=utc_now_naive)

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
    # ⚠️ 必须 nullable。手机号是可选的，而 `unique=True` 的唯一索引在
    # Postgres 里**允许多个 NULL、只允许一个空串** —— 若这列 NOT NULL，
    # 注册时只能塞 ""，于是**第二个**没填手机号的用户永远注册不进来
    # （撞 ix_users_phone_number 报 500，实测踩到）。
    phone_number = Column(String, nullable=True, unique=True, index=True)  # 手机号（可空）
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

    def to_dict(self, include_password: bool = False) -> dict[str, Any]:
        result = {
            "id": self.id,
            "user_name": self.user_name,
            "user_id": self.user_id,
            "phone_number": self.phone_number,
            "avatar": self.avatar,
            # shipping_address 是真实存在的列，但 to_dict 一直漏了它 ——
            # 表现是「收货地址」在个人信息里永远是空。一并补上。
            "shipping_address": self.shipping_address,
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


class TaskRecord(Base):
    """定时任务定义表"""
    __tablename__ = "task_records"

    __table_args__ = (
        Index("ix_task_records_user_status", "user_id", "status"),
        Index("ix_task_records_next_run", "next_run_at"),
    )

    id = Column(String(64), primary_key=True)                    # 任务唯一ID (UUID)
    user_id = Column(String(64), nullable=False, index=True)     # 所属用户
    name = Column(String(200), nullable=False)                    # 任务名称
    task_type = Column(String(32), nullable=False, index=True)    # price/stock/coupon/rank/shop
    status = Column(String(20), nullable=False, default="active", index=True)  # active/paused/completed/failed

    # 调度配置
    cron_expression = Column(String(64), nullable=True)   # cron 表达式，如 "*/30 * * * *"
    interval_seconds = Column(Integer, nullable=True)      # 间隔秒数（与cron二选一）

    # 任务参数（JSON，各类型任务参数不同）
    # price:  {"product_name": "iPhone 15", "target_price": 5000, "platform": "taobao"}
    # stock:  {"product_name": "...", "platform": "taobao"}
    # coupon: {"keyword": "手机", "platform": "taobao"}
    # rank:   {"keyword": "蓝牙耳机", "product_name": "...", "platform": "taobao"}
    # shop:   {"shop_name": "...", "platform": "taobao"}
    task_params = Column(JSON, nullable=False, default=dict)

    # 通知配置
    notify_enabled = Column(Boolean, nullable=False, default=True)  # 是否启用通知
    notify_channels = Column(JSON, nullable=False, default=list)    # ["sse", "email"] 预留

    # 运行统计
    last_run_at = Column(DateTime, nullable=True)         # 上次执行时间
    next_run_at = Column(DateTime, nullable=True)         # 下次执行时间
    run_count = Column(Integer, nullable=False, default=0) # 总执行次数
    last_result = Column(JSON, nullable=True)              # 最近一次执行结果摘要

    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "task_type": self.task_type,
            "status": self.status,
            "cron_expression": self.cron_expression,
            "interval_seconds": self.interval_seconds,
            "task_params": self.task_params or {},
            "notify_enabled": bool(self.notify_enabled),
            "notify_channels": self.notify_channels or [],
            "last_run_at": format_utc_datetime(self.last_run_at) if self.last_run_at else None,
            "next_run_at": format_utc_datetime(self.next_run_at) if self.next_run_at else None,
            "run_count": self.run_count,
            "last_result": self.last_result,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }


class TaskExecutionLog(Base):
    """任务执行日志表"""
    __tablename__ = "task_execution_logs"

    __table_args__ = (
        Index("ix_task_exec_logs_task", "task_id", "started_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="running")  # running/success/failed/timeout
    started_at = Column(DateTime, default=utc_now_naive)
    finished_at = Column(DateTime, nullable=True)
    duration_ms = Column(Integer, nullable=True)                     # 执行耗时（毫秒）
    result_data = Column(JSON, nullable=True)                        # 执行结果数据
    error_message = Column(Text, nullable=True)                      # 错误信息

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task_id": self.task_id,
            "status": self.status,
            "started_at": format_utc_datetime(self.started_at),
            "finished_at": format_utc_datetime(self.finished_at) if self.finished_at else None,
            "duration_ms": self.duration_ms,
            "result_data": self.result_data,
            "error_message": self.error_message,
        }


class PriceSnapshot(Base):
    """价格快照表 — 用于历史趋势图"""
    __tablename__ = "price_snapshots"

    __table_args__ = (
        Index("ix_price_snap_product_time", "product_id", "snapshot_at"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(String(128), nullable=False, index=True)    # 商品唯一标识
    product_name = Column(String(500), nullable=False)
    platform = Column(String(32), nullable=False)                    # taobao/pdd/jd
    price = Column(Integer, nullable=False)                          # 价格（分）
    original_price = Column(Integer, nullable=True)                  # 原价（分）
    coupon_amount = Column(Integer, nullable=True)                   # 优惠券面额（分）
    stock_status = Column(String(32), nullable=True)                 # in_stock/out_of_stock/unknown
    shop_name = Column(String(200), nullable=True)
    snapshot_at = Column(DateTime, default=utc_now_naive, index=True)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "product_id": self.product_id,
            "product_name": self.product_name,
            "platform": self.platform,
            "price": self.price,
            "original_price": self.original_price,
            "coupon_amount": self.coupon_amount,
            "stock_status": self.stock_status,
            "shop_name": self.shop_name,
            "snapshot_at": format_utc_datetime(self.snapshot_at),
        }


class Conversation(Base):
    """对话会话表 - 事件溯源架构"""
    __tablename__ = "conversations"

    __table_args__ = (
        Index("ix_conversations_user_updated", "user_id", "updated_at"),
        Index("ix_conversations_agent_status", "agent_id", "status"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    thread_id = Column(String(64), nullable=False, unique=True, index=True)  # LangGraph thread_id
    user_id = Column(String(64), nullable=False, index=True)  # 用户 ID
    agent_id = Column(String(64), nullable=False, index=True)  # Agent ID

    title = Column(String(200), nullable=False, default="新对话")
    status = Column(String(20), nullable=False, default="active", index=True)  # active/archived/deleted
    is_pinned = Column(Boolean, nullable=False, default=False)

    # 元数据（存储附件、标签等扩展信息）
    conv_metadata = Column("metadata", JSON, nullable=False, default=dict)

    # 消息历史（JSONB 数组，事件溯源）
    messages = Column(JSONB, nullable=False, default=list)

    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.thread_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "title": self.title,
            "status": self.status,
            "is_pinned": bool(self.is_pinned),
            "metadata": self.conv_metadata or {},
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at),
        }


class ShoppingDecision(Base):
    """购物档案（决策库）记录

    每条记录以整份 ShoppingRecord（phase 五状态机 + 分段字段）存进 data 列，
    前端以「整册同步」方式工作，故此处不做字段级拆解，保持与前端契约一致。
    主键为 (user_id, id) 复合键：记录 id 由前端生成（如 nd-1），跨用户会重复。
    """

    __tablename__ = "shopping_decisions"

    id = Column(String, primary_key=True)  # 前端生成的记录 id（如 nd-1 / us-3）
    user_id = Column(String, primary_key=True)  # 归属用户
    phase = Column(String, nullable=False, default="need", index=True)  # need/candidate/decided/using/dropped
    data = Column(JSONB, nullable=False, default=dict)  # 完整 ShoppingRecord
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    __table_args__ = (
        Index("ix_shopping_decisions_user_phase", "user_id", "phase"),
    )

    def to_dict(self) -> dict[str, Any]:
        return self.data or {}

class MCPServer(Base):
    """MCP 服务器配置（2026-09-22 新增）。

    字段对齐前端 `web-v2/src/apis/mcp_api.js` 已消费的形状。
    运行态字段（status / tools_count / heartbeat）由 /test 接口刷新，
    不做后台轮询 —— 避免常驻开销。
    """

    __tablename__ = "mcp_servers"

    id = Column(String, primary_key=True)  # 形如 mc-<uuid8>
    name = Column(String, nullable=False, unique=True)  # 唯一名，运行时按它查
    type = Column(String, nullable=False, default="stdio")  # stdio / http / sse
    endpoint = Column(String, nullable=False, default="")  # 命令（stdio）或 URL
    desc = Column(String, nullable=False, default="")
    enabled = Column(Boolean, nullable=False, default=True)
    env_json = Column(JSONB, nullable=False, default=dict)  # stdio 子进程环境变量
    # ── 运行态（/test 刷新）──
    status = Column(String, nullable=False, default="idle")  # connected/failed/idle/testing
    tools_count = Column(Integer, nullable=False, default=0)
    heartbeat = Column(String, nullable=False, default="—")
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        """转成前端消费的形状（字段名与 mcp_api.js 契约一致）。

        ⚠️ **不回传 env 值**：里面是凭据（TAOBAO_SESSION / API key 等），
        明文返回给前端等于泄露。只回传键名，让界面能显示「配了哪些变量」，
        但不暴露值。修改凭据走 PUT（提交新值覆盖）。
        """
        env_keys = sorted((self.env_json or {}).keys())
        return {
            "id": self.id,
            "name": self.name,
            "type": self.type,
            "endpoint": self.endpoint,
            "desc": self.desc or "",
            "enabled": bool(self.enabled),
            "env_keys": env_keys,
            "status": self.status or "idle",
            "tools": self.tools_count or 0,
            "heartbeat": self.heartbeat or "—",
            "source": "custom",
        }


# ══════════════════════════════════════════════════════════════
# 采购规划（planning agent）—— 2026-09-24 新增
# ══════════════════════════════════════════════════════════════

class PlanningRun(Base):
    """一次采购规划任务实例。

    与 `TaskRecord` 的区别（有意不合并）：
      · TaskRecord 是**周期性监控**（间隔/cron、下次执行、反复跑）
      · PlanningRun 是**一次性规划**（有明确的收敛终点，跑完就沉淀成方案）
    两者的生命周期、调度语义、前端形态都不同，共用一张表会立刻需要
    「一半字段对另一半为空」的分支。

    与 `conversations` 的区别：工作台是「任务实例」不是「对话线程」，
    图的推进与用户的拍板都挂在 run 上，不混进通用对话历史。
    """

    __tablename__ = "planning_runs"

    id = Column(String(64), primary_key=True)                 # 形如 pr-<uuid8>
    user_id = Column(String(64), nullable=False, index=True)  # 与其它表同口径 str(users.id)
    # running 跑图中 / awaiting 等用户拍板 / converged 已收敛 / failed 出错
    status = Column(String(20), nullable=False, default="running", index=True)

    # ── 入口页收敛出的结构化参数 ──
    scene = Column(String(64), nullable=False, default="")
    budget = Column(String(64), nullable=False, default="")     # 保留用户原话（「¥6万」），不强行转数字
    duration = Column(String(64), nullable=False, default="")
    constraints = Column(JSON, nullable=False, default=list)    # ["有老人", "要静音"]

    subject = Column(String(120), nullable=False, default="")   # 本次要买的主体（如「洗地机」）

    # ── 决策图当前快照 ──
    # 存快照而非只存事件：工作台刷新要能一次拿全，不该扫全表重放。
    # 每次图变更由 planning_service 覆盖写入。
    graph = Column(JSONB, nullable=False, default=dict)         # {nodes: [...], edges: [...]}
    meta = Column(JSONB, nullable=False, default=dict)          # {totalExpected, subject, scene}

    # ── 当前待确认的问题（右栏浮出的那张卡）──
    question = Column(JSONB, nullable=True)                     # {text, options: [{key,label,primary}]}

    # 用户对上一次提问选了哪个选项（option 的 key）。
    # 续跑时 `advance` 把它翻成一句话喂回 agent —— agent 是 ReAct 循环，
    # 多给一条输入它自己接着判断，不需要算「从哪一步接」。
    answer_pick = Column(String(64), nullable=True)

    # 回答的**副本**：选项标签 + 当时的提问原文。
    #
    # ⚠️ 为什么不能只存 key、事后再去 question 里翻：
    # 用户一点选项，`question` 就被清空了（那是「当前待确认」的字段）。
    # 续跑时再读它只能拿到空对象，拼出「关于「」，我选：opt0」这种废话，
    # 模型据此跑偏（实测：用户选「推隔音窗」，模型去查了「隔音门」）。
    answer_label = Column(String(200), nullable=True)
    answer_question = Column(Text, nullable=True)

    # agent 的对话历史（可 JSON 化的精简形式）。
    #
    # 中断续跑时必须带上，否则 agent 从零开始 —— 搜过的、排除过的全部重做。
    # 实测一次运行因此把 6 次搜索做成了 12 次，候选池从 ~20 膨胀到 42。
    # 只留最后 60 条（见 planning_service._persist_history）。
    messages = Column(JSONB, nullable=False, default=list)

    # agent 累积的产物：{candidates, excluded, selected, risks, dimensions}
    #
    # ⚠️ 为什么单独存一份，而不是从 graph 反推：
    # 走法由模型定，候选/排除/选中都在 agent state 里，图只记关键节点。
    # agent 跑完 state 就没了，收尾生成交付物时读不到 —— 交付物会全是空的。
    # 所以推演过程中边跑边落这里（见 planning_service._persist_products）。
    products = Column(JSONB, nullable=False, default=dict)

    # ═══════════════════════════════════════════════════════════════════
    # 交付状态
    # ═══════════════════════════════════════════════════════════════════
    # 用户原话：「点击生成交付即可在历史记录将待交付转变成已交付」。
    #
    # 为什么要**落库**而不是前端记一个 ref：交付状态是这条采购记录跨会话
    # 的属性 —— 关掉页面、换台设备、三天后回来看，它还是「已交付」。
    # 前端 ref 一刷新就没了，历史列表也就无从显示。
    #
    # ⚠️ 与 `status` 的区别（两个不同的东西，别混）：
    #   status      **推演**的状态：running / awaiting / converged / failed
    #   delivered   用户的**交付动作**：跑完了 ≠ 交付了。收敛只说明方案算好了，
    #               交付是用户确认「这份我拿走了」——要留痕、要能在历史里区分。
    delivered_at = Column(DateTime, nullable=True)

    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        """转成前端消费的形状（字段名与 planning_api.js 契约一致）。"""
        return {
            "id": self.id,
            "status": self.status,
            "scene": self.scene or "",
            "budget": self.budget or "",
            "duration": self.duration or "",
            "constraints": self.constraints or [],
            "subject": self.subject or "",
            "graph": self.graph or {"nodes": [], "edges": []},
            "meta": self.meta or {},
            "question": self.question,
            "answer_pick": self.answer_pick,
            "answer_label": self.answer_label,
            "answer_question": self.answer_question,
            "products": self.products or {},
            # 交付状态：前端据此显示「待交付 / 已交付」，历史列表也用它
            "delivered_at": format_utc_datetime(self.delivered_at),
            "delivered": bool(self.delivered_at),
            "error": self.error,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at) if self.updated_at else None,
        }


class PlanningEvent(Base):
    """采购规划的**只追加**事件流水 —— 执行流与图变更的同一本账。

    为什么与 PlanningRun.graph 分两处（而不是只留事件、或只留快照）：
      · 快照（run.graph）服务「刷新后一次拿全」——读最新一行即可
      · 事件（本表）服务「过程可回看」——左栏执行流要按时间顺序展开，
        且断线后要能从 after_seq 续传
    只留快照就回放不出过程；只留事件则每次拉图都要扫全表重放。
    两者由 planning_service 在同一处写入，不会漂。

    kind 取值（刻意收窄，够用即可 —— 不学 chat 的 15 种事件）：
      phase       阶段推进     payload {phase, label}
      think       思考         payload {title, detail?}
      retrieve    检索         payload {title, detail?}
      call        工具调用     payload {title, detail?}
      produce     产出         payload {title, detail?}
      graph       图变更       payload {nodes, edges}   ← 增量，前端合并
      question    待确认       payload {text, options}
      deliverable 交付物       payload {id, name, state, meta, progress?}
      done        结束         payload {status}
    """
    __tablename__ = "planning_events"

    __table_args__ = (
        # 续传按 (run_id, seq) 走，这是唯一的读路径
        Index("ix_planning_events_run_seq", "run_id", "seq"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, index=True)
    seq = Column(Integer, nullable=False)                      # run 内自增，从 1 开始
    kind = Column(String(20), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, default=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "kind": self.kind,
            "payload": self.payload or {},
            "at": format_utc_datetime(self.created_at),
        }


# ══════════════════════════════════════════════════════════════
# 代购送礼（gift agent）—— 2026-09-24 新增
# ══════════════════════════════════════════════════════════════
#
# 与 PlanningRun 刻意不合并：任务性质不同（见 web-v2/.impeccable.md 的分区豁免）。
#   · planning = **决策收敛**：N 个候选 → 1 个方案，核心产物是决策图
#   · gift     = **意义建构**：1 个意图 → 一段过程 → 1 份礼物，核心产物是人物档案
# 共用一张表会立刻需要「一半字段对另一半为空」的分支 —— 图与档案的形态、
# 生命周期、前端承载方式都不同。

class GiftRun(Base):
    """一次送礼推演任务实例。"""

    __tablename__ = "gift_runs"

    id = Column(String(64), primary_key=True)                 # 形如 gr-<uuid8>
    user_id = Column(String(64), nullable=False, index=True)
    status = Column(String(20), nullable=False, default="running", index=True)

    # ── 入口页收敛出的送礼情境 ──
    recipient = Column(String(64), nullable=False, default="")   # 送给谁
    occasion = Column(String(64), nullable=False, default="")    # 为了什么
    budget = Column(Integer, nullable=False, default=0)          # 预算（元）
    signals = Column(JSON, nullable=False, default=list)         # 用户勾选的在意点 key

    # ── 中栏：人物档案（逐步被写活）──
    # 每组 {key, label, icon, text, note, state, source, danger}
    # state 三态是硬要求：confirmed 已确认 / inferred 智能推测 / pending 待确认
    profile = Column(JSONB, nullable=False, default=list)
    # 底部「当前理解」{text, from}
    understanding = Column(JSONB, nullable=False, default=dict)
    # 档案抬头 {name, initial, meta, sub, completeness}
    profile_head = Column(JSONB, nullable=False, default=dict)

    # ⚠️ 2026-09-27：这里曾被误加 `delivered_at`（见下方说明），已移除 ——
    # 送礼侧还没有交付流程，字段加了但 to_dict 与数据库都没有，导致
    # `select gift_runs.delivered_at` 直接报 UndefinedColumn（入口页 500）。
    # 需要时再加，并且要**同时**改 to_dict 与迁移。

    error = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "status": self.status,
            "recipient": self.recipient or "",
            "occasion": self.occasion or "",
            "budget": int(self.budget or 0),
            "signals": self.signals or [],
            "profile": self.profile or [],
            "understanding": self.understanding or {},
            "profileHead": self.profile_head or {},
            "error": self.error,
            "created_at": format_utc_datetime(self.created_at),
            "updated_at": format_utc_datetime(self.updated_at) if self.updated_at else None,
        }


class GiftEvent(Base):
    """送礼推演的**只追加**事件流水。

    与 PlanningEvent 同样分「快照 + 事件」两处：快照服务刷新恢复，
    事件服务过程回看 + 断线续传（seq 单调）。

    kind 与前端 `useGiftWorkbench.apply()` 的 `ev.t` **一一对应** ——
    这是刻意的：前端状态机不改，只把产出源从 mock 换成后端。

      stage        阶段推进     {key}
      step         步骤状态     {key, status, evidence?, why?}
      live         实时描述     {key, text, more}
      excluded     排除候选     {name, why}
      profile      档案更新     {key, state, text?, note?}
      understanding 当前理解    {text, from}
      deliverable  交付物       {key, state, data?}
      done         结束         {}
    """
    __tablename__ = "gift_events"

    __table_args__ = (
        Index("ix_gift_events_run_seq", "run_id", "seq"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_id = Column(String(64), nullable=False, index=True)
    seq = Column(Integer, nullable=False)
    kind = Column(String(24), nullable=False)
    payload = Column(JSONB, nullable=False, default=dict)
    created_at = Column(DateTime, default=utc_now_naive)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "kind": self.kind,
            "payload": self.payload or {},
            "at": format_utc_datetime(self.created_at),
        }
