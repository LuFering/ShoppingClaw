# 任务 API（/api/tasks/*)

定时监控任务（价格/库存/优惠券/排名/店铺）。实现：APScheduler
(`AsyncIOScheduler` in `src/services/scheduler_service.py`) + 执行器
`src/services/task_executors/`（price/stock/coupon/rank/shop）。
数据落 `task_records`（元数据）、`task_execution_logs`（执行日志）、
`price_snapshots`（价签快照）。

## 端点一览

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/tasks` | 创建任务 |
| GET | `/api/tasks` | 任务列表 |
| GET | `/api/tasks/{task_id}` | 任务详情 |
| PUT | `/api/tasks/{task_id}` | 更新任务（含暂停/恢复） |
| DELETE | `/api/tasks/{task_id}` | 删除任务 |
| POST | `/api/tasks/{task_id}/trigger` | 立即手动触发一次 |
| GET | `/api/tasks/{task_id}/logs` | 执行日志 |
| GET | `/api/tasks/price-history/{product_id}` | 某商品价格历史曲线数据 |

## 创建任务 Body

```json
{
  "name": "盯价格",
  "task_type": "price",
  "cron_expression": "0 9 * * *",
  "interval_seconds": 3600,
  "task_params": { "product_id": "10000001", "target_price": 199 },
  "notify_enabled": true
}
```

| 字段 | 说明 |
| --- | --- |
| `task_type` | `price` / `stock` / `coupon` / `rank` / `shop` |
| `cron_expression` 与 `interval_seconds` | 二选一触发方式（cron 或 interval） |
| `task_params` | 执行器参数（product_id/关键词等，依类型而异） |
| `status` | `active` / `paused`（更新接口可切换） |

## 执行模型

- 服务重启时从 `task_records` 恢复 active 任务（lifespan Phase 3）。
- `trigger` 手动执行记录到 logs；执行异常不中断调度器。
- 价格任务把快照写入 `price_snapshots`，供 `price-history/{product_id}`
  画折线图。
