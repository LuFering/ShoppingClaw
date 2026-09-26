import itertools
import logging
import threading
import shutil
import subprocess
import os
import json
import re
from typing import Any, Callable, Dict, List

logger = logging.getLogger(__name__)

# ==========================================
# MCP Server Registry (MCP服务器注册表)
# ==========================================
# 存放所有已配置的 MCP 服务器信息。
#
# type 类型:
#   - http:      远程 HTTP JSON-RPC
#   - stdio:     本地 stdio 子进程（如 sinataoke_cn）
#   - streamableHttp: SSE 流式 HTTP（如京东联盟 MCP，暂不可用）
#
# 注意: JD 不再通过 MCP 层 — 京东 SDK 已直接在 @tool 装饰器的 research/tools.py 中集成
MCP_SERVERS: Dict[str, Dict[str, Any]] = {
    # 淘宝/拼多多导购 MCP — 本地 stdio 子进程
    "taobao_mcp": {
        "type": "stdio",
        # 2026-09-21 启用：原挂起理由（sinataoke_cn.cmd 是 Windows 批处理）已不成立——
        # _ensure_stdio_process 在非 Windows 下会去掉 .cmd 后缀走 shutil.which，
        # 且容器内已全局安装 sinataoke_cn@2.0.9（Node v20），实测可正常握手与调用。
        "enabled": True,
        "description": "淘宝联盟 + 多多进宝商品搜索与转链（sinataoke_cn MCP）",
        "command": "sinataoke_cn",
        "env": {
            "ENV_URL": "https://config.sinataoke.cn/api/mcp/secret",
            "ENV_SECRET": "url:mcp.sinataoke.cn",
            "ENV_OVERRIDE": "false",
            # 以下凭据从系统环境变量注入（.env 已配置）
            "TAOBAO_SESSION": os.getenv("TAOBAO_SESSION", ""),
            "TAOBAO_PID": os.getenv("TAOBAO_PID", ""),
        },
    },
}

# 硬编码配置的**快照**（迁移到 DB 时用；MCP_SERVERS 之后会被 DB 内容覆盖）
# 用 deepcopy 隔离，避免 DB 加载改动 MCP_SERVERS 时污染这份基线。
_HARDCODED_MCP_SERVERS: Dict[str, Dict[str, Any]] = json.loads(json.dumps(MCP_SERVERS))

def _db_url() -> str:
    """取 PostgreSQL 连接串（与 pg_manager 同一套环境变量）。"""
    url = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL") or ""
    if url:
        return url
    user = os.getenv("POSTGRES_USER", "postgres")
    pwd = os.getenv("POSTGRES_PASSWORD", "postgres")
    host = os.getenv("POSTGRES_HOST", "postgres")
    port = os.getenv("POSTGRES_PORT", "5432")
    db = os.getenv("POSTGRES_DB", "shoppingclaw")
    return f"postgresql+asyncpg://{user}:{pwd}@{host}:{port}/{db}"


async def _with_own_engine(fn):
    """在**独立引擎**上执行 fn(session)，用完即 dispose。

    为什么不用 pg_manager：它的共享连接池锁绑定在主 serve loop 上，
    而本模块的迁移/加载跑在 `run_in_executor` 的线程里（自己的临时 loop），
    跨循环访问共享池会抛
    「Future attached to a different loop」。
    这里开短连接、用完释放 —— 与 RedisCache.sync_get 的思路一致。
    """
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    engine = create_async_engine(_db_url(), pool_pre_ping=True)
    try:
        session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
        async with session_factory() as session:
            return await fn(session)
    finally:
        await engine.dispose()


def migrate_hardcoded_to_db() -> None:
    """把硬编码的 MCP 配置幂等写进 DB（首次启动时）。

    只写 DB 里**不存在**的条目，不覆盖已有配置 —— 用户在管理页改过的设置
    不能被启动流程冲掉。失败只记 warning，不影响服务启动。
    """
    try:
        import asyncio

        from sqlalchemy import select

        from src.storage.postgres.models_business import MCPServer

        async def _run(session) -> None:
            for name, cfg in _HARDCODED_MCP_SERVERS.items():
                exists = (
                    await session.execute(
                        select(MCPServer.id).where(MCPServer.name == name)
                    )
                ).scalar_one_or_none()
                if exists:
                    continue
                session.add(
                    MCPServer(
                        id=f"mc-{name[:8]}",
                        name=name,
                        type=cfg.get("type", "stdio"),
                        endpoint=cfg.get("command", "") or cfg.get("url", ""),
                        desc=cfg.get("description", ""),
                        enabled=bool(cfg.get("enabled", True)),
                        env_json=cfg.get("env", {}) or {},
                    )
                )
                logger.info(f"[MCP] 已迁移硬编码配置到 DB: {name}")
            await session.commit()

        # 在同步上下文里跑异步（本函数由 to_thread 调用，无运行中的 loop）
        asyncio.run(_with_own_engine(_run))
    except Exception as exc:
        logger.warning(f"[MCP] 硬编码配置迁移失败（忽略，继续用硬编码）: {exc}")


def load_mcp_servers_from_db() -> None:
    """从 DB 读配置并**合并**进 MCP_SERVERS。

    合并语义：
      · DB 里 enabled 的条目 → 覆盖同名硬编码（DB 是用户配置的真相）
      · DB 里没有的硬编码条目 → 保留（兜底，避免迁移失败导致 MCP 全挂）
      · DB 里 enabled=False 的同名条目 → 从运行表移除（用户禁用了）

    DB 不可用时静默跳过，MCP_SERVERS 保持硬编码内容 —— MCP 服务不因
    DB 故障而中断。
    """
    try:
        import asyncio

        from sqlalchemy import select

        from src.storage.postgres.models_business import MCPServer

        async def _run(session) -> list[dict]:
            """取 ORM 的**原始字段**，不用 to_dict()。

            ⚠️ `to_dict()` 是给前端的**脱敏视图**（env 只回传键名），
            用它来构造运行配置会丢掉凭据 —— 实测导致 MCP 子进程
            因缺少 ENV_URL / TAOBAO_SESSION 而启动即退出（rc=1）。
            这里直接读 ORM 的 env_json，拿真实值。
            """
            result = await session.execute(select(MCPServer))
            return [
                {
                    "name": r.name,
                    "type": r.type,
                    "endpoint": r.endpoint or "",
                    "desc": r.desc or "",
                    "enabled": bool(r.enabled),
                    "env": dict(r.env_json or {}),
                }
                for r in result.scalars().all()
            ]

        rows = asyncio.run(_with_own_engine(_run))
        if not rows:
            logger.info("[MCP] DB 中无 MCP 配置，沿用硬编码")
            return

        loaded = 0
        for row in rows:
            name = row["name"]
            if not row.get("enabled", True):
                MCP_SERVERS.pop(name, None)
                continue
            entry: dict[str, Any] = {
                "type": row.get("type", "stdio"),
                "enabled": True,
                "description": row.get("desc", ""),
                "env": row.get("env", {}) or {},
            }
            if entry["type"] == "stdio":
                entry["command"] = row.get("endpoint", "")
            else:
                entry["url"] = row.get("endpoint", "")
            MCP_SERVERS[name] = entry
            loaded += 1
        logger.info(f"[MCP] 从 DB 加载 {loaded} 条配置")
    except Exception as exc:
        logger.warning(f"[MCP] 从 DB 加载配置失败（忽略，沿用硬编码）: {exc}")


def warmup_mcp_servers() -> None:
    """预加载所有启用的 stdio MCP 子进程（应用启动时调用一次）。

    冷启动成本（8s 等进程 + 3s initialize）原本由**第一次真实调用**承担，
    用户在首轮对话里白等十几秒。这里提前付掉，之后的调用只付网络往返。

    失败不影响主流程：MCP 不可用时工具列表为空，智能体照常工作。
    """
    # 2026-09-22：先把硬编码迁移进 DB（幂等），再从 DB 加载（覆盖硬编码）
    migrate_hardcoded_to_db()
    load_mcp_servers_from_db()

    for name, cfg in MCP_SERVERS.items():
        if not cfg.get("enabled", True):
            continue
        if cfg.get("type") != "stdio":
            continue
        try:
            proc = _ensure_stdio_process(name, cfg)
            if proc is None:
                logger.warning(f"[MCP] 预加载 {name} 失败（首次调用时重试）")
                continue
            logger.info(f"[MCP] 预加载完成: {name}")
        except Exception as exc:
            logger.warning(f"[MCP] 预加载 {name} 异常（忽略）: {exc}")


def get_mcp_serve_names() -> List[str]:
    """
    获取所有已注册的 MCP 服务器名称。
    
    返回:
        服务器名称列表，例如 ["mock_inventory_mcp"]
    """
    return list(MCP_SERVERS.keys())

# ── stdio 进程管理 ──
# 全局缓存：每个 stdio MCP 服务器对应一个持久子进程
_stdio_processes: Dict[str, subprocess.Popen] = {}

# 子进程启动锁（2026-09-22）。
# 为什么需要：`_ensure_stdio_process` 的「检查是否已启动 → Popen → 握手」
# 是一段读-改-写，无锁时并发调用会各起一个子进程、互相干扰 stdin/stdout，
# 后写的覆盖前一个，前一个成为孤儿并被误判为「启动后立即退出」。
# 实测：预热（后台线程）与首次对话（请求线程）并发时必现，
# 而串行的 /test 接口从不出错 —— 这就是竞态的铁证。
# 锁是**进程级**的：只在真正需要启动时竞争，已启动的走快返回。
_stdio_start_lock = threading.Lock()


def _drain_stderr(proc: subprocess.Popen, server_name: str) -> None:
    """后台消费子进程 stderr，防止管道缓冲区写满导致子进程阻塞。

    ⚠️ 这是 2026-09-22 定位到的真实根因：
      `stderr=PIPE` 若无人读取，缓冲区（通常 64KB）写满后
      子进程的 write 会阻塞 —— MCP 服务卡在写启动日志上，
      永远处理不到 stdin 的 initialize 请求，表现为握手超时。
      实测：PIPE → 失败；DEVNULL → 7.1 秒成功。

    这里用独立线程持续读走 stderr 并转写到应用日志，
    既避免阻塞，又不像 DEVNULL 那样丢失排查线索。
    """
    if proc.stderr is None:
        return
    try:
        for line in proc.stderr:
            text = (line or "").rstrip()
            if text:
                logger.debug(f"[MCP:{server_name}] {text[:300]}")
    except Exception:
        pass  # 进程退出时读会抛异常，属正常

# initialize 握手的最长等待（秒）。
# 冷启动（Node 模块首次加载）可能十几秒，热启动 1-2 秒。
MCP_INIT_TIMEOUT_S = 30


def _read_line_with_timeout(
    proc: subprocess.Popen, *, timeout: float, poll_interval: float = 0.5
) -> str:
    """在超时内轮询等待子进程输出一行。

    为什么不用 readline() 直接读：管道上的 readline() 是**阻塞**的，
    进程不吐字就永久挂住（表现为整条对话流卡死）。
    这里改成「轮询 + 超时」：每次检查进程是否还活着、有没有数据可读。

    Returns:
        读到的一行（不含换行）；超时或无数据返回空串。
    """
    import select
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            return ""  # 进程已退出，不会再吐字
        try:
            # select 探可读性（POSIX）；stdout 是管道，有数据时立即返回
            ready, _, _ = select.select([proc.stdout], [], [], poll_interval)
            if ready:
                line = proc.stdout.readline()
                if line and line.strip():
                    return line
        except Exception:
            # select 不可用（如 Windows）→ 退化为短睡后重试
            time.sleep(poll_interval)
    return ""


def _ensure_stdio_process(server_name: str, server_config: Dict[str, Any]) -> subprocess.Popen | None:
    """确保 stdio MCP 子进程已启动并完成初始化，返回可用进程。

    并发安全：整段「检查 → 启动 → 握手」持锁执行。
    无锁时并发调用会各起一个子进程、互相干扰 stdin/stdout
    （实测：预热与首次对话并发必现「启动后立即退出」，而串行调用从不失败）。
    """
    # 快路径：已启动且在运行 → 不取锁直接返回
    proc = _stdio_processes.get(server_name)
    if proc is not None and proc.poll() is None:
        return proc

    with _stdio_start_lock:
        # 双检：等锁期间可能已被别的线程启动
        proc = _stdio_processes.get(server_name)
        if proc is not None and proc.poll() is None:
            return proc
        if proc is not None:
            logger.warning(f"[MCP] stdio 进程 {server_name} 已退出，重新启动")
            _stdio_processes.pop(server_name, None)

        return _spawn_stdio_process(server_name, server_config)


def _spawn_stdio_process(server_name: str, server_config: Dict[str, Any]) -> subprocess.Popen | None:
    """实际启动子进程并握手（由 _ensure_stdio_process 持锁调用）。"""

    command = server_config.get("command", "")
    if not command:
        logger.error(f"[MCP] stdio 服务器 {server_name} 缺少 command 配置")
        return None

    # 跨平台命令解析：
    #   - Windows: 全局 npm 包的 .cmd shim 位于 %APPDATA%\npm\
    #   - Linux/macOS: npm -g 的 bin 在 PATH 中（无 .cmd 后缀），用 shutil.which 解析
    cmd_path: str | None = None
    if os.name == "nt":
        cmd_path = os.path.join(os.environ.get("APPDATA", ""), "npm", command)
        if not os.path.exists(cmd_path):
            logger.error(f"[MCP] 找不到命令: {cmd_path}")
            return None
    else:
        bare = command[:-4] if command.endswith(".cmd") else command
        cmd_path = shutil.which(bare)
        if not cmd_path:
            logger.error(
                f"[MCP] 找不到命令: {bare}（请确认已在服务器安装 Node.js 并 "
                f"npm install -g {bare}）"
            )
            return None

    env = {**os.environ, **server_config.get("env", {})}
    try:
        proc = subprocess.Popen(
            [cmd_path],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8", errors="replace",
            env=env,
        )
    except Exception as exc:
        logger.error(f"[MCP] 启动 stdio 进程 {server_name} 失败: {exc}")
        return None

    # ⚠️ 必须在等进程就绪**之前**启动 stderr 消费线程：
    #    服务启动瞬间就会写日志，晚一步就可能已经填满缓冲区。
    threading.Thread(
        target=_drain_stderr, args=(proc, server_name), daemon=True
    ).start()

    import time
    # 2026-09-22：从 8 秒缩到 3 秒 —— 之前留了过长的固定等待，
    # 而真正需要的是「等 initialize 响应」（见下面的轮询）。
    time.sleep(3)
    if proc.poll() is not None:
        _, err = proc.communicate(timeout=5)
        logger.error(
            f"[MCP] stdio 进程 {server_name} 启动后立即退出: {err[:300]}"
            f"（env 键数={len((server_config.get('env') or {}))}）"
        )
        return None

    # 执行 MCP initialize 握手
    #
    # ⚠️ 2026-09-22 修复：原实现是「sleep(3) 后单次 readline()」。
    #    MCP 服务（sinataoke_cn）**首次**启动要加载 Node 模块，
    #    3 秒往往还没就绪 → readline() 读到空 → 判定失败。
    #    实测同一函数连续三次调用：第 1 次失败、第 2/3 次成功
    #    （第 2 次起 Node require cache 生效，启动变快）。
    #    现在改为**轮询等待**，冷启动也能等到。
    try:
        proc.stdin.write(json.dumps({"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"ShoppingClaw","version":"1.0"}},"id":1}) + "\n")
        proc.stdin.flush()

        line = _read_line_with_timeout(
            proc, timeout=MCP_INIT_TIMEOUT_S, poll_interval=0.5
        )
        if not line.strip():
            logger.error(
                f"[MCP] stdio 进程 {server_name} initialize 无响应"
                f"（等待 {MCP_INIT_TIMEOUT_S}s）"
            )
            proc.terminate()
            return None
        r = json.loads(line)
        svr = r.get("result", {}).get("serverInfo", {})
        logger.info(f"[MCP] {server_name} 初始化成功: {svr.get('name')} v{svr.get('version')}")

        proc.stdin.write(json.dumps({"jsonrpc":"2.0","method":"notifications/initialized","params":{}}) + "\n")
        proc.stdin.flush()
        _stdio_processes[server_name] = proc
        return proc
    except Exception as exc:
        logger.error(f"[MCP] stdio 进程 {server_name} 初始化失败: {exc}")
        proc.terminate()
        return None


def _get_stdio_tool_specs(server_name: str, server_config: Dict[str, Any]) -> List[Dict[str, Any]]:
    """从 stdio MCP 服务器拉取工具列表。

    ═══════════════════════════════════════════════════════════════════
    ⚠️ 2026-09-27 修 bug：单次 readline 会读到半行，整个工具清单丢失
    ═══════════════════════════════════════════════════════════════════

    原先这里是 `time.sleep(5)` 之后**只读一行**就 `json.loads`。工具清单
    是个几十 KB 的大 JSON，子进程往管道里写时会被**分片**，`readline()`
    可能只拿到前半截 —— 解析报 `Expecting ',' delimiter: line 1 column 5094`，
    异常被吞掉返回 `[]`，于是**一个工具都加载不到**。

    后果不是「少几个工具」而是**整条链路瘫掉**：`search_products` 拿不到
    taobao 工具 → 每次搜索都返回「没有返回结果，换个词试试」→ agent 反复
    换词重搜（实测换了 5 个词）→ 最后没有候选、没有选中、交付物全空。

    而且这个空结果会被 `get_tools_from_all_servers` 的 TTL 缓存住 5 分钟，
    期间怎么重试都是坏的。

    修法与 `_call_stdio_tool` 一致：**按行读到能解析出 JSON 为止**，
    而不是读一次就当真。同时持 IO 锁 —— 管道是单条的，并发读会串包。
    """
    proc = _ensure_stdio_process(server_name, server_config)
    if proc is None or proc.stdin is None or proc.stdout is None:
        return []
    try:
        import time
        req_id = next(_stdio_req_seq)
        with _stdio_io_lock:
            proc.stdin.write(json.dumps({
                "jsonrpc": "2.0", "method": "tools/list", "params": {}, "id": req_id,
            }) + "\n")
            proc.stdin.flush()

            # 读到能解析出**匹配 id** 的 JSON 为止。半行/非 JSON 行（子进程
            # 日志）跳过重试，直到超时上限 —— 与 _call_stdio_tool 同一套。
            deadline = time.time() + MCP_CALL_TIMEOUT_S
            r = None
            while time.time() < deadline:
                line = proc.stdout.readline()
                if not line or not line.strip():
                    time.sleep(0.1)
                    continue
                try:
                    candidate = json.loads(line)
                except Exception:
                    continue   # 半行或日志行，继续读
                if candidate.get("id") == req_id:
                    r = candidate
                    break
                logger.warning(f"[MCP] 丢弃孤儿响应 id={candidate.get('id')}（期望 {req_id}）")

        if r is None:
            logger.error(f"[MCP] {server_name} 的 tools/list 未收到匹配响应")
            return []
        tools = r.get("result", {}).get("tools", [])
        specs = []
        seen_names: set[str] = set()
        for t in tools:
            raw_name = t.get("name", "")
            # LLM 接口要求工具名 ^[a-zA-Z0-9_-]+$（MCP 原名常含 '.'，如 taobao.searchMaterial）：
            # 对外用净化名，原始名存 _mcp_tool_name 供实际调用回查
            safe_name = re.sub(r"[^a-zA-Z0-9_-]", "_", raw_name) or "mcp_tool"
            while safe_name in seen_names:
                safe_name += "_"
            seen_names.add(safe_name)
            schema = t.get("inputSchema", {}) or {}
            # —— 对已知必填缺失的淘宝搜索工具做修补：接口要求 q 与 cat 至少一个，
            # 但 MCP schema 声明 required=[]（导致 LLM 以为可都不传 → 400）。
            # 这里强制把 required 标成 ["q"]，并保留 cat 可选项，让 LLM 至少传搜索词。
            # （q/cat 兜底在 mcp_tool_adapter 的 stdio executor 里再做一层）
            if raw_name == "taobao.searchMaterial":
                props = schema.get("properties", {}) or {}
                if "q" in props and (schema.get("required") is None or len(schema.get("required", [])) == 0):
                    schema = {**schema, "required": ["q"]}
            specs.append({
                "name": safe_name,
                "description": t.get("description", ""),
                "inputSchema": schema,
                "_mcp_tool_name": raw_name,
                "_mcp_server_name": server_name,
                "_mcp_server_type": "stdio",
            })
        return specs
    except Exception as exc:
        logger.error(f"[MCP] 从 {server_name} 拉取工具列表失败: {exc}")
        return []


# 单次 tools/call 的最大等待（秒）。正常响应 1-2 秒；
# 设为 20 是为了容忍远程 API 的偶发长尾，同时避免整条流被挂死。
MCP_CALL_TIMEOUT_S = 20



# stdio 往返锁 + 自增请求 id。
#
# 为什么需要锁：MCP 子进程是**单管道** stdin/stdout，多个调用并发写会交错、
# 盲读会串包。购前助手会并行发 2-3 个搜索关键词，实测（2026-09-21 22:07:35）
# 三个并发 searchMaterial 里有两个 `json.loads("")` 失败 —— 就是这里的竞态。
# 锁把「写请求 + 读响应」这一对操作串行化，代价是并发搜索变成排队，
# 但换来的是结果正确；相比静默丢结果，这个代价值得。
_stdio_io_lock = threading.Lock()
_stdio_req_seq = itertools.count(1000)


def _call_stdio_tool(server_name: str, server_config: Dict[str, Any], tool_name: str, arguments: Dict[str, Any]) -> Any:
    """调用 stdio MCP 工具（同步版本，必须在线程中调用以避免阻塞事件循环）。

    并发安全：持锁完成「写请求 → 读响应」的完整往返，避免请求交错与串包。
    """
    proc = _ensure_stdio_process(server_name, server_config)
    if proc is None or proc.stdin is None or proc.stdout is None:
        return {"error": "stdio MCP 进程不可用"}

    req_id = next(_stdio_req_seq)
    with _stdio_io_lock:
        try:
            import time
            proc.stdin.write(json.dumps({
                "jsonrpc": "2.0", "method": "tools/call",
                "params": {"name": tool_name, "arguments": arguments},
                "id": req_id,
            }) + "\n")
            proc.stdin.flush()

            # 2026-09-22：去掉 sleep(5) 的固定等待。
            # 原来无论响应多久都白睡 5 秒 —— 2-3 个并发搜索就是 15 秒纯等待。
            # 改成「按行读到匹配 id 的响应为止」：响应通常 1-2 秒就回，
            # 立刻返回；只有异常时才等到 MCP_CALL_TIMEOUT_S 上限。
            deadline = time.time() + MCP_CALL_TIMEOUT_S
            r = None
            for _ in range(3):
                if proc.stdout in (None,):
                    break
                line = proc.stdout.readline()
                if not line or not line.strip():
                    # 还没吐字：短睡后重试，直到超时上限
                    if time.time() >= deadline:
                        break
                    time.sleep(0.1)
                    continue
                try:
                    candidate = json.loads(line)
                except Exception:
                    continue  # 非 JSON 行（子进程日志等）跳过
                if candidate.get("id") == req_id:
                    r = candidate
                    break
                logger.warning(f"[MCP] 丢弃孤儿响应 id={candidate.get('id')}（期望 {req_id}）")
                if time.time() >= deadline:
                    break

            if r is None:
                logger.error(f"[MCP] stdio 工具 {tool_name} 未收到匹配响应 (id={req_id})")
                return {"error": "MCP 未返回匹配的响应"}

            content = r.get("result", {}).get("content", [{}])
            if content and isinstance(content, list) and len(content) > 0:
                return content[0].get("text", json.dumps(r))
            return json.dumps(r)
        except Exception as exc:
            logger.error(f"[MCP] stdio 工具调用 {tool_name} 失败: {exc}")
            return {"error": str(exc)}


async def call_stdio_tool_async(
    server_name: str,
    server_config: Dict[str, Any],
    tool_name: str,
    arguments: Dict[str, Any],
) -> Any:
    """调用 stdio MCP 工具（异步版本，使用线程池避免阻塞事件循环）。"""
    import asyncio
    return await asyncio.to_thread(
        _call_stdio_tool, server_name, server_config, tool_name, arguments
    )

_tools_cache: Dict[str, Any] = {"specs": None, "at": 0.0}
_TOOLS_CACHE_TTL = 300   # 秒。工具清单是启动期固定的，5 分钟足够保守


async def get_tools_from_all_servers(force: bool = False) -> List[Dict[str, Any]]:
    """
    从所有注册的 MCP 服务器拉取并聚合工具。

    注意：
    这里返回的不是可执行的 Callable 函数，而是工具的描述字典 (Tool Spec)。
    `mcp_tool_adapter` 会负责把这些字典转换为 LangChain 可用的 Tool 对象。

    ⚠️ 2026-09-24 修复（两处）：
    1. **不再阻塞事件循环**。本函数虽是 async，但内部 `_get_stdio_tool_specs()`
       是同步阻塞的（握手 + `time.sleep(5)` 等 tools/list 响应），直接在协程里
       调用会**卡死整个事件循环**。实测：建一次采购规划 run 时，`/api/system/health`
       这种不碰 DB 的探针也一起停了 5.13 秒 —— 前端表现为工作台长时间卡在
       「正在恢复任务…」。改为 `asyncio.to_thread`，与 `call_stdio_tool_async`
       同一处理（那个函数早就这么做了，只是这条**工具列表**路径漏了）。
    2. **加 TTL 缓存**。`_get_stdio_tool_specs` 里有一个**无条件**的
       `time.sleep(5)`（即便子进程早已预热），所以每次调用都实打实付 5 秒。
       原先主智能体只在建图时调一次，问题不明显；采购规划每个阶段都取一次
       工具，代价立刻放大。工具清单是启动期固定的，缓存 5 分钟足够保守。

    返回:
        聚合后的所有工具描述列表
    """
    import time as _time

    if not force and _tools_cache["specs"] is not None:
        if _time.time() - _tools_cache["at"] < _TOOLS_CACHE_TTL:
            return _tools_cache["specs"]

    all_tools_specs: List[Dict[str, Any]] = []

    for server_name, server_config in MCP_SERVERS.items():
        # 挂起的 MCP 服务器不拉取工具，避免 Linux 下阻塞整个工具加载流程
        if not server_config.get("enabled", True):
            logger.info(f"MCP 服务器 {server_name} 已挂起（enabled=False），跳过工具拉取。")
            continue
        try:
            logger.info(f"正在从 MCP 服务器拉取工具: {server_name}")
            srv_type = server_config.get("type", "http")
            
            if srv_type == "stdio":
                # 丢到线程池：_get_stdio_tool_specs 内部是阻塞 IO（含 time.sleep），
                # 直接 await 会卡死事件循环（见函数 docstring 的实测记录）
                import asyncio
                tools_specs = await asyncio.to_thread(
                    _get_stdio_tool_specs, server_name, server_config
                )
            else:
                logger.warning(f"MCP 服务器 {server_name} 的 type={srv_type} 暂未实现")
                tools_specs = []
                
            all_tools_specs.extend(tools_specs)
            logger.info(f"成功从 {server_name} 加载了 {len(tools_specs)} 个工具。")
        except Exception as e:
            # 工程性防御：一个 MCP Server 挂了，不能影响其他 Server 的工具加载
            logger.error(f"从 MCP 服务器 {server_name} 拉取工具失败: {e}", exc_info=True)
            continue

    # ⚠️ **空结果不进缓存**。
    # 拉取失败时各 server 会返回 []，若照常缓存，接下来 5 分钟（TTL）内
    # 每次调用都拿到空清单 —— 实测一次解析失败后整条搜索链路瘫了 5 分钟，
    # 界面表现为「agent 换了好几个词都搜不到东西」。
    # 缓存的意义是省下重复拉取的 5 秒，不是把失败也固化下来。
    if all_tools_specs:
        _tools_cache["specs"] = all_tools_specs
        _tools_cache["at"] = _time.time()
    else:
        logger.warning("[MCP] 工具清单为空，**不缓存**（下次调用重试）")
    return all_tools_specs