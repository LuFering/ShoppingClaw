"""监控任务工具集（2026-09-23 新增）—— 购后助手专属。

背景：
  16 个 buildin 工具里**没有任何创建监控任务的工具**。用户说
  "帮我盯一下这款的价格，降价提醒我" 时，Agent 只能口头答应 ——
  而主动助理页面上写着「监控运行中」是假的（DB 里长期 0 条任务）。
  这个工具补上「对话说了真的算」这一段。

归属：post_purchase（与 set_reminder 同族）。
  master 的 _MASTER_FORBIDDEN_TOOLS 已明确把「用户数据（属购后助手职责）」
  划给购后；监控任务是用户对未来的意图，与提醒语义同族。

与 set_reminder 的分工：
  · set_reminder  → 写进档案记录的 reminders 数组（人看的清单）
  · create_monitor_task → 写 task_records + 注册调度器（机器会真的去跑）

  ⚠️ 断链已补：set_reminder 带 due 时会同时调这里落一条定时任务，
     否则「提醒」永远躺在 DB 里不会响（见 archive_tools.set_reminder）。

设计约束：
  1. 写库 + 注册调度器两步都要做，只写库不会跑。
  2. 全部 try/except 包裹 —— 建任务失败不能打断对话。
  3. task_type 必须是已注册的执行器类型，否则调度器会抛 ValueError。
  4. 用户口径统一 str(users.id)（与 task_router 的 _uid 一致）。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from src.agents.common.toolkits.registry import tool

logger = logging.getLogger(__name__)

# ── 与 task_executors/__init__.py 的 EXECUTORS 保持一致 ──
# 2026-09-29：`stock` → `deal`（优惠到期）。补货监控已下线 ——
# 导购 MCP 不提供库存数据，见 task_executors/deal_executor.py 顶部。
VALID_TASK_TYPES = ("price", "deal", "coupon", "rank", "shop", "agent")

# 店铺名的形貌特征。用于挡住「把商品名当店铺名」这种错配 ——
# 实测过：模型会给 `shop_name` 填「iPhone 15 Pro」。
_SHOP_HINTS = ("店", "旗舰", "官方", "专营", "专卖", "商城", "自营", "超市")


def _looks_like_shop(name: str) -> bool:
    """粗判是不是店铺名。宁可宽松（放过可疑的），也不要卡死正常输入 ——
    但商品名（「iPhone 15 Pro」这种）必须被挡住。"""
    n = str(name or "")
    return any(h in n for h in _SHOP_HINTS)

# 每类任务需要的参数（缺了执行器会直接返回错误）
REQUIRED_PARAMS = {
    "price": ("product_name",),
    "deal": ("product_name",),
    "coupon": ("keyword",),
    "rank": ("keyword", "product_name"),
    "shop": ("shop_name",),
    "agent": ("prompt",),
}

DEFAULT_INTERVAL_HOURS = 6     # 价格默认 6 小时一次（淘宝价格变动没那么频繁）
MIN_INTERVAL_HOURS = 1
MAX_INTERVAL_HOURS = 720       # 30 天


class CreateMonitorTaskInput(BaseModel):
    task_type: str = Field(
        ...,
        description="监控类型：price(降价) / deal(优惠到期) / coupon(优惠券) / rank(榜单排名) / shop(店铺活动)",
    )
    target: str = Field(..., description="监控对象：商品名、关键词、或店铺名")
    target_price: str = Field("", description="目标价（元，仅 price 类型用），如 '2899'")
    interval_hours: int = Field(
        DEFAULT_INTERVAL_HOURS, description="执行间隔小时数，默认 6，最小 1，最大 720"
    )
    task_name: str = Field("", description="任务名（可选，默认自动生成）")


def _clean_task_name(target: str, task_type: str, given: str) -> str:
    label = {
        "price": "盯价", "deal": "盯优惠", "coupon": "盯券",
        "rank": "盯排名", "shop": "盯店铺", "agent": "定时执行",
    }.get(task_type, "监控")
    if given and given.strip():
        return given.strip()[:60]
    return f"{label} · {target[:24]}"[:60]


def _parse_target_price(raw: str) -> int | None:
    """'2899' / '¥2899' / '2899元' / '2899.5' → 分。解析不出来返回 None。"""
    if raw is None:
        return None
    import re

    text = str(raw).strip()
    if not text:
        return None
    m = re.search(r"(\d+(?:\.\d+)?)", text.replace(",", ""))
    if not m:
        return None
    try:
        cents = int(round(float(m.group(1)) * 100))
    except (TypeError, ValueError):
        return None
    return cents if cents > 0 else None


@tool(
    category="buildin",
    tags=["监控", "盯价", "定时任务", "购后"],
    display_name="创建监控任务",
    icon="🔔",
    args_schema=CreateMonitorTaskInput,
)
async def create_monitor_task(
    user_id: str,
    task_type: str,
    target: str,
    target_price: str = "",
    interval_hours: int = DEFAULT_INTERVAL_HOURS,
    task_name: str = "",
) -> str:
    """创建一个定时监控任务，让系统持续盯着某个目标并在有动静时提醒用户。

    用户说出「盯一下价格」「降价告诉我」「优惠快到期提醒我」这类意图时使用。
    创建后任务会按间隔自动执行，命中时出现在主动助理页面。

    ⚠️ **补货 / 库存类监控不可用**：数据源（导购 MCP）不提供库存信息，
    系统无法判断商品是否缺货或有货。用户提这类诉求时**如实告知做不到**，
    不要用 shop / price 等其它类型顶替 —— 那会让用户以为在盯补货，
    实际盯的是别的东西。

    参数:
        user_id: 用户ID
        task_type: 监控类型 price(降价)/deal(优惠到期)/coupon(优惠券)/rank(排名)/shop(店铺活动)。
                   **没有 stock** —— 补货监控不可用（无数据源）。
        target: 监控对象，商品名 / 关键词 / 店铺名。
                注意 shop 类型必须传**店铺名**（如「小米官方旗舰店」），
                传商品名会被拒绝。
        target_price: 目标价（元），仅 price 类型需要，如 '2899'
        interval_hours: 执行间隔小时数，默认 6
        task_name: 任务名（可选）
    """
    logger.info(f"[Tool] 创建监控任务: {user_id} | {task_type} | {target}")

    try:
        # ── 1) 校验类型 ──
        task_type = str(task_type or "").strip().lower()
        if task_type not in VALID_TASK_TYPES:
            return (
                f"错误: 未知监控类型 '{task_type}'，可选 {', '.join(VALID_TASK_TYPES)}。"
                f"注意：**补货/库存类监控不可用**（数据源不提供库存信息），"
                f"请如实告知用户，不要用其它类型代替。"
            )

        target = str(target or "").strip()
        if not target:
            return "错误: 缺少监控对象（target）"

        # ⚠️ 语义护栏（2026-09-29 加）：类型与目标必须对得上。
        #
        # 实测 bug：用户说「盯 iPhone 15 Pro 的**补货**」，模型自选了
        # `shop` 类型、把**商品名**填进 `shop_name`，然后回复
        # 「补货监控已经挂上了……一旦到货就通知你」—— 三处都错，
        # 而且承诺了系统做不到的事。
        #
        # 类型校验原本只查「是不是合法值」，`shop` 合法所以放行了。
        # 这里补一层「形貌判据」：店铺名得有店铺的样子。
        if task_type == "shop" and not _looks_like_shop(target):
            return (
                f"错误: 「{target}」看起来是**商品名**，不是店铺名。"
                f"shop 类型要盯的是店铺（如「小米官方旗舰店」）。"
                f"如果你想盯这个商品，请用 price（盯价）或 deal（优惠到期）。"
            )

        # ── 2) 校验间隔 ──
        # 注意用 `is None` 而不是 `or`：传 0 是想"尽快跑"，应夹到最小值 1；
        # 用 `or` 会把 0 当假值静默换成默认 6，与文档说明的"最小 1"不符。
        hours = DEFAULT_INTERVAL_HOURS if interval_hours is None else interval_hours
        try:
            hours = int(hours)
        except (TypeError, ValueError):
            hours = DEFAULT_INTERVAL_HOURS
        hours = max(MIN_INTERVAL_HOURS, min(MAX_INTERVAL_HOURS, hours))

        # ── 3) 组装 task_params（字段名必须与各执行器一致）──
        params: dict = {"platform": "taobao"}
        if task_type == "price":
            params["product_name"] = target
            cents = _parse_target_price(target_price)
            if cents:
                params["target_price"] = cents
        elif task_type == "deal":
            params["product_name"] = target
        elif task_type == "coupon":
            params["keyword"] = target
        elif task_type == "rank":
            params["keyword"] = target
            params["product_name"] = target
        elif task_type == "shop":
            params["shop_name"] = target
        elif task_type == "agent":
            params["prompt"] = target
            params.pop("platform", None)

        # 缺必填参数时明确告知，而不是建一个跑不动的任务
        missing = [k for k in REQUIRED_PARAMS[task_type] if not params.get(k)]
        if missing:
            return f"错误: {task_type} 类型缺少参数 {', '.join(missing)}"

        # ── 4) 写库 + 注册调度器（两步都不能少）──
        from src.services.scheduler_service import get_scheduler
        from src.storage.postgres.manager import pg_manager
        from src.storage.postgres.models_business import TaskRecord
        from src.utils.datetime_utils import utc_now_naive

        task_id = str(uuid.uuid4())
        now = utc_now_naive()
        record = TaskRecord(
            id=task_id,
            user_id=str(user_id),
            name=_clean_task_name(target, task_type, task_name),
            task_type=task_type,
            status="active",
            interval_seconds=hours * 3600,
            task_params=params,
            notify_enabled=True,
            notify_channels=["sse"],
            created_at=now,
            updated_at=now,
        )

        async with pg_manager.get_async_session_context() as session:
            session.add(record)
            await session.commit()

        scheduler = get_scheduler()
        await scheduler.add_task(record)

        logger.info(f"[Tool] 监控任务已创建并注册: {task_id} ({task_type})")

        # ── 5) 给模型一段能直接复述给用户的确认文案 ──
        freq = f"每 {hours} 小时" if hours < 24 else f"每 {hours // 24} 天"
        price_note = ""
        if task_type == "price" and params.get("target_price"):
            price_note = f"，目标 ¥{params['target_price'] / 100:.0f}"
        name = record.name
        return json.dumps(
            {
                "status": "success",
                "task_id": task_id,
                "task_name": name,
                "task_type": task_type,
                "target": target,
                "frequency": freq,
                "target_price": params.get("target_price"),
                "message": f"已创建监控任务「{name}」{price_note}，{freq}检查一次，有动静会在主动助理里提醒你。",
            },
            ensure_ascii=False,
        )

    except Exception as e:
        logger.error(f"创建监控任务失败: {e}")
        return f"创建监控任务失败: {str(e)}"


class ListMonitorTasksInput(BaseModel):
    include_paused: bool = Field(False, description="是否包含已暂停的任务")


@tool(
    category="buildin",
    tags=["监控", "查询", "购后"],
    display_name="查看监控任务",
    icon="📡",
    args_schema=ListMonitorTasksInput,
)
async def list_monitor_tasks(user_id: str, include_paused: bool = False) -> str:
    """列出用户当前在盯的监控任务，含最近一次执行结果与时间。

    用户问「我在盯什么」「帮我看看监控任务」时使用。

    参数:
        user_id: 用户ID
        include_paused: 是否包含已暂停的任务
    """
    logger.info(f"[Tool] 查看监控任务: {user_id}")
    try:
        from sqlalchemy import select

        from src.storage.postgres.manager import pg_manager
        from src.storage.postgres.models_business import TaskRecord

        async with pg_manager.get_async_session_context() as session:
            stmt = select(TaskRecord).where(TaskRecord.user_id == str(user_id))
            if not include_paused:
                stmt = stmt.where(TaskRecord.status == "active")
            rows = (await session.execute(
                stmt.order_by(TaskRecord.created_at.desc()).limit(50)
            )).scalars().all()

            if not rows:
                return json.dumps(
                    {"status": "empty", "message": "当前没有监控任务。", "tasks": []},
                    ensure_ascii=False,
                )

            tasks = []
            for t in rows:
                last = t.last_result or {}
                tasks.append({
                    "id": t.id,
                    "name": t.name,
                    "type": t.task_type,
                    "target": (t.task_params or {}).get(
                        "product_name",
                        (t.task_params or {}).get(
                            "keyword", (t.task_params or {}).get("shop_name", "")),
                    ),
                    "status": t.status,
                    "interval_hours": (t.interval_seconds or 0) // 3600 or None,
                    "run_count": t.run_count or 0,
                    "last_result": last.get("status") if isinstance(last, dict) else None,
                    "last_run_at": (
                        t.last_run_at.strftime("%Y-%m-%d %H:%M") if t.last_run_at else None
                    ),
                })

            return json.dumps(
                {"status": "success", "count": len(tasks), "tasks": tasks},
                ensure_ascii=False,
            )
    except Exception as e:
        logger.error(f"查看监控任务失败: {e}")
        return f"查看监控任务失败: {str(e)}"
