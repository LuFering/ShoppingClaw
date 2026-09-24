"""购物档案（决策库）API 路由

契约与前端 `web-v2/src/apis/decisions_api.js` 对齐。

═══════════════════════════════════════════════════════════════════════
2026-09-25 改为**逐条 CRUD** —— 起因是一次真实的数据丢失
═══════════════════════════════════════════════════════════════════════

原实现只有两个写端点：`PUT /batch`（先 DELETE 全部、再整批写入）与
`DELETE /`（清空全部）。配套的前端是「页面 deep-watch 全量保存」。

这个模式有一个**必然**的数据丢失路径，两条写入方互不知情：

    购后助手 save_to_archive  → 写**单条**
    档案页 watch(records)     → saveAll() → DELETE 全部 + 重写

于是：Agent 归档一条 → 用户打开档案页（页面加载的是**旧快照**）→
页面自动保存 → **Agent 那条被抹掉**。

这不是理论风险：2026-09-25 验证时，一次 `PUT /batch` 就把 user 2 的
21 条真实档案压成了 1 条（autovacuum 已回收，无法恢复）。

**所以本文件现在只提供逐条语义**，并且：

  · `PUT /batch` 保留但**改为「按 id 增量 upsert」**，不再删任何东西 ——
    这是为了兼容还在用它的前端；新代码不该再用。
  · 新增 `POST`（单条建/改）、`DELETE /{id}`（删单条）。
  · `DELETE /`（清空）**需要显式确认参数** —— 全清是不可逆的破坏性操作，
    不该由一个不带参数的请求触发。
"""
from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import delete, select
from sqlalchemy.orm.attributes import flag_modified

from server.utils.auth_middleware import get_required_user
from server.utils.user_store import User
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import ShoppingDecision

router = APIRouter(prefix="/decisions", tags=["decisions"])


def _uid(user: User) -> str:
    """取稳定的用户标识（与 chat 路由保持一致：用 users.id）"""
    return str(getattr(user, "id", None) or getattr(user, "user_id", "anonymous"))


def _norm_incoming(rec: dict) -> dict:
    """把前端传来的一条记录规范成可落库的形状。

    只做**结构**校验，不碰业务字段 —— 档案的字段集还在演进，
    在这里做字段级白名单会让新增字段静默丢失。
    """
    if not isinstance(rec, dict):
        raise HTTPException(400, "记录必须是对象")
    rid = str(rec.get("id") or "").strip()
    if not rid:
        raise HTTPException(400, "记录缺少 id")
    out = dict(rec)
    out["id"] = rid
    out["phase"] = str(rec.get("phase") or "need")
    return out


async def _upsert_one(session, uid: str, rec: dict) -> bool:
    """按 (user_id, id) 落一条。返回是否新建。"""
    row = (
        await session.execute(
            select(ShoppingDecision).where(
                ShoppingDecision.user_id == uid, ShoppingDecision.id == rec["id"]
            )
        )
    ).scalar_one_or_none()

    if row is None:
        session.add(
            ShoppingDecision(id=rec["id"], user_id=uid, phase=rec["phase"], data=rec)
        )
        return True

    row.phase = rec["phase"]
    row.data = rec
    # JSONB 列原地替换也要打标记，否则 SQLAlchemy 可能认为没变化
    flag_modified(row, "data")
    return False


# ══════════════════════════════════════════════════════════
# 读
# ══════════════════════════════════════════════════════════

@router.get("")
async def list_decisions(
    phase: str | None = Query(default=None),
    current_user: User = Depends(get_required_user),
):
    """当前用户的全部档案。可按 phase 过滤（如只看待确认）。"""
    uid = _uid(current_user)
    async with pg_manager.get_async_session_context() as session:
        q = select(ShoppingDecision).where(ShoppingDecision.user_id == uid)
        if phase:
            q = q.where(ShoppingDecision.phase == phase)
        rows = (await session.execute(q)).scalars().all()
    return {"success": True, "data": [r.data for r in rows]}


@router.get("/{record_id}")
async def get_decision(record_id: str, current_user: User = Depends(get_required_user)):
    uid = _uid(current_user)
    async with pg_manager.get_async_session_context() as session:
        row = (
            await session.execute(
                select(ShoppingDecision).where(
                    ShoppingDecision.user_id == uid, ShoppingDecision.id == record_id
                )
            )
        ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "记录不存在")
    return {"success": True, "data": row.data}


# ══════════════════════════════════════════════════════════
# 写（逐条）
# ══════════════════════════════════════════════════════════

@router.post("")
async def create_or_update(
    record: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
):
    """建或改**一条**记录（按 id upsert）。

    幂等：同一个 id 提交两次不会产生两条 —— 前端可以放心重试。
    """
    uid = _uid(current_user)
    rec = _norm_incoming(record)
    async with pg_manager.get_async_session_context() as session:
        created = await _upsert_one(session, uid, rec)
        await session.commit()
    return {"success": True, "created": created, "data": rec}


# ⚠️ `/batch` 必须声明在 `/{record_id}` **之前** —— FastAPI 按声明顺序匹配，
# 否则 `PUT /decisions/batch` 会被 `/{record_id}` 吃掉（record_id="batch"）。

@router.put("/batch")
async def sync_decisions(
    body: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
):
    """兼容旧的「整册同步」调用 —— **但不再删除任何记录**。

    旧实现是「先 DELETE 该用户全部 → 再整批写入」，这正是丢数据的根源
    （见文件头）。现在改为**按 id 增量 upsert**：
      · 提交里有的 → 建或更新
      · 提交里没有的 → **保持不动**（不再被抹掉）

    语义变化是有意的：从「这份提交是全量真相」改成「这是要写入的一批」。
    调用方若真的想删除，必须走 `DELETE /{id}` 逐条删 —— 破坏性操作不能藏在
    一个 PUT 里。
    """
    uid = _uid(current_user)
    records = body.get("records") or []
    if not isinstance(records, list):
        raise HTTPException(400, "records 必须是数组")

    created = updated = skipped = 0
    async with pg_manager.get_async_session_context() as session:
        for raw in records:
            try:
                rec = _norm_incoming(raw)
            except HTTPException:
                skipped += 1
                continue
            if await _upsert_one(session, uid, rec):
                created += 1
            else:
                updated += 1
        await session.commit()

    return {"success": True, "created": created, "updated": updated,
            "skipped": skipped, "count": created + updated}


@router.put("/{record_id}")
async def update_decision(
    record_id: str,
    patch: dict[str, Any] = Body(...),
    current_user: User = Depends(get_required_user),
):
    """改一条已存在的记录（**局部更新**：只覆盖传了的字段）。

    与 POST 的区别：这里要求记录已存在，且把传入字段**合并**进原记录，
    而不是整条替换 —— 前端只改一个 phase 时不必回传整份 data。
    """
    uid = _uid(current_user)
    async with pg_manager.get_async_session_context() as session:
        row = (
            await session.execute(
                select(ShoppingDecision).where(
                    ShoppingDecision.user_id == uid, ShoppingDecision.id == record_id
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "记录不存在")

        merged = {**(row.data or {}), **patch, "id": record_id}
        row.data = merged
        row.phase = str(merged.get("phase") or row.phase or "need")
        flag_modified(row, "data")
        await session.commit()
    return {"success": True, "data": merged}


@router.delete("/{record_id}")
async def delete_decision(record_id: str, current_user: User = Depends(get_required_user)):
    """删**一条**记录。"""
    uid = _uid(current_user)
    async with pg_manager.get_async_session_context() as session:
        res = await session.execute(
            delete(ShoppingDecision).where(
                ShoppingDecision.user_id == uid, ShoppingDecision.id == record_id
            )
        )
        await session.commit()
    if not res.rowcount:
        raise HTTPException(404, "记录不存在")
    return {"success": True, "deleted": record_id}


# ══════════════════════════════════════════════════════════
# 批量（兼容旧前端；语义已改）
# ══════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════
# 清空（破坏性，需显式确认）
# ══════════════════════════════════════════════════════════

@router.delete("")
async def reset_decisions(
    confirm: bool = Query(default=False),
    current_user: User = Depends(get_required_user),
):
    """清空当前用户的**全部**档案。

    ⚠️ 需要 `?confirm=true`。全清不可逆，不该由一个不带参数的请求触发 ——
    之前它可以被误调用，而前端 `reset()` 里还写着「后端未实现时静默」，
    一旦真的实现就会静默清库。
    """
    if not confirm:
        raise HTTPException(
            400, "清空全部档案是不可逆操作，请显式传 ?confirm=true"
        )
    uid = _uid(current_user)
    async with pg_manager.get_async_session_context() as session:
        res = await session.execute(
            delete(ShoppingDecision).where(ShoppingDecision.user_id == uid)
        )
        await session.commit()
    return {"success": True, "deleted": res.rowcount or 0}
