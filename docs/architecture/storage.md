# 存储与对话持久化架构

> 本文是全仓库**最重要的工程文档**：对话能否可靠持久化、Redis 故障时系统
> 是否还能工作，都取决于这里描述的模型。改存储相关代码前必读。

## 1. 总体原则

```
写入路径（消息/线程）              读取路径（历史）
┌──────────┐   ① 先落    ┌──────────────┐      ┌──────────────┐
│ 业务代码  │ ──────────▶ │ PostgreSQL    │ ───▶ │ History API  │
└──────────┘              │ (主真相/JSONB)│      │ (PG 优先)     │
      │                   └──────────────┘      └──────────────┘
      │ ② 再镜像（失败只告警）
      ▼
┌──────────────┐   Redis 不可用 ──▶ 降级
│ Redis        │                   ▼
│ (影子/加速层) │            ┌──────────────┐
└──────────────┘            │ memory_store │ (进程内，仅兜底)
                            └──────────────┘
```

- **PostgreSQL = 唯一主真相**：线程元数据在 `conversations` 表，
  消息以 JSONB 数组**追加式**存储（事件溯源风格）。
- **Redis = 影子层**：提供快速的线程列表/消息读取与缓存；**允许丢、允许错**，
  绝不因 Redis 故障阻断主链路。
- **memory_store = 进程内兜底**：Redis 之外的最终 fallback，重启即失。
- 三段式访问封装：`MessageStoreBridge`（`src/services/redis_store.py`）对上层
  提供统一接口 `create_thread/get_messages/add_message/...`，内部：Redis 优先
  → 任一命令异常降级 memory_store，**永不向上抛错**。

## 2. 数据模型

### conversations 表（线程）

| 列 | 类型 | 说明 |
| --- | --- | --- |
| id | varchar PK | 线程 id（uuid，前端以此为 thread_id） |
| user_id | varchar | 属主用户（比较 users.id 时需 `users.id::text`，两边类型不同） |
| agent_id | varchar | 关联 agent（如 `MasterAgent`） |
| title | varchar | 对话标题（首轮由 LLM 生成） |
| is_pinned | bool | 置顶 |
| created_at / updated_at | timestamptz | 排序用 |
| messages | jsonb | 消息数组，见下 |

### 消息对象（JSONB 数组元素）

```json
{
  "role": "user",
  "content": "帮我看看 200 元以内的耳机",
  "type": "user",
  "timestamp": "2026-09-08T09:12:00+00:00"
}
```

| 字段 | 说明 |
| --- | --- |
| `role` | `user` / `assistant` / `system` |
| `type` | `user` / `ai` / `thinking` / `tool_call` / `tool_result` / `product_card` …（消息类型，前端按此渲染） |
| `content` | 文本内容；商品卡片等结构化消息可能是 dict |
| `timestamp` | **UTC ISO-8601 字符串**（`datetime.now(timezone.utc).isoformat()`） |

历史遗留：更早的消息可能缺 `timestamp` 或缺 content（假 AI 空消息），读取端
按数组顺序渲染不受影响；不要依赖所有历史消息都有完整字段。

### 其它业务表（`src/storage/postgres/models_business.py`）

`users` · `operation_logs`（审计） · `agent_configs` · `knowledge_faq` ·
`knowledge_retrieval_log` · `task_records` · `task_execution_logs` ·
`price_snapshots`。LangGraph Checkpointer 数据也在 PG（独立表，后端自动管理）。

### Redis 键布局（影子层）

| 键 | 内容 |
| --- | --- |
| `thread:{id}` | 线程元数据 hash（title/pinned/created 等） |
| `thread:{id}:messages` | 消息 list |
| `user:{uid}:threads` | 用户线程列表 |
| `cache:*` | 商品/API 缓存（sync_get/sync_set） |
| 限流键 | `chat:user:{uid}` 滑动窗口计数 |

## 3. 写入时序（一次对话）

关键规则：**任何消息先落 PG（try/except 保护），成功后再镜像 Redis
（try/except），顺序不可颠倒**——早期版本曾因 Redis 先写且未容错，
Redis 一抖就导致整条消息丢进 PG。

```
用户发送 query
  ├─ 1. thread 不存在时由路由层创建（bridge 先建 → PG 双写）
  ├─ 2. 用户消息 {role:user,type:user,timestamp} → PG add_message（try）
  │      └─ bridge.add_message 镜像（try，失败仅 warning）
  ├─ 3. Agent 流式执行…（thinking/tool 事件只进 SSE 流，不落库）
  ├─ 4. 结束：若积累了内容 → AI 消息 {role:assistant,type:ai} → PG（try）
  │      └─ bridge 镜像（try）；无内容则**不落空消息**（有守卫）
  ├─ 5. 标题生成 → update_thread（PG/bridge）
  └─ 异常/断连兜底：已累积内容仍尽力保存（PG 优先 + bridge，均 try）
```

实现位置：`src/services/chat_stream_service.py`（用户消息/AI 消息/thinking/
商品卡片/异常分支的保存点都遵循上述顺序）。

## 4. 读取路径

`GET /api/chat/agent/{agent_id}/history?thread_id=...`：

1. 有 PG 会话 → 读 `conversations.messages`，非空即返回 `{"history": [...]}`
2. PG 无结果/异常 → 降级 `store_bridge.get_messages(thread_id)`
3. 线程列表 `GET /api/chat/threads` 与删除 `DELETE` 同理（PG 优先）

## 5. Redis 连接纪律（重要事故教训）

`redis.asyncio` 的连接池/锁**惰性绑定**首次使用它的那个事件循环；之后被
另一个事件循环（线程里的 `asyncio.run`、重连后的 loop）触碰会抛
`Lock bound to a different event loop` / `Task got Future attached to a
different loop`。曾因此导致对话存储全链路 500。

合法访问路径只有三条：

| 场景 | 路径 |
| --- | --- |
| async 代码（uvicorn serve loop 内） | 共享池：lifespan 启动时 `get_redis_cache().connect()` 预热，之后直接复用 |
| 同步代码（普通函数/线程） | `RedisCache.sync_get / sync_set`（每次独立短连接，自动关闭） |
| 存储桥接 | `MessageStoreBridge._call`（内部先 `_ensure_connected`，任何异常降级） |

**禁止**：在 running loop 中 `asyncio.run(...)` 包装共享池操作；用
ThreadPoolExecutor 把共享客户端丢进别的线程；手写 `redis.from_url` 客户端
后跨 loop 复用。`cache_decorator.py` 的同步包装只许走 `sync_*`。

## 6. 时间戳约定

- 消息/审计等业务时间：`datetime.now(timezone.utc).isoformat()`（UTC）。
- 耗时统计（time_cost/总时长）用 `loop.time()` 单调钟**只做差值，不入库**。
- 前端不消费消息 timestamp（按顺序渲染），但排序与将来导入需要它，保持规范。

## 7. 一致性边界（必须接受的现实）

- PG 与 Redis 是**最终一致**：镜像写失败只告警，后续读以 PG 为准自动修正。
- `memory_store` 兜底写入的数据在容器重启后消失，属可接受降级。
- 线程删除：PG 与 Redis 分别尽力删除，单边失败留残键不影响主链路
  （残键仅浪费空间，可在故障手册找到清理脚本）。
