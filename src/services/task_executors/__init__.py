"""
任务执行器包

每种任务类型对应一个异步执行函数，签名统一为:
    async def execute(task: TaskRecord) -> dict

返回 dict 即为 last_result。
"""
from src.services.task_executors.price_executor import execute as price_executor
from src.services.task_executors.stock_executor import execute as stock_executor
from src.services.task_executors.coupon_executor import execute as coupon_executor
from src.services.task_executors.rank_executor import execute as rank_executor
from src.services.task_executors.shop_executor import execute as shop_executor
from src.services.task_executors.agent_executor import execute as agent_executor

EXECUTORS = {
    "price": price_executor,
    "stock": stock_executor,
    "coupon": coupon_executor,
    "rank": rank_executor,
    "shop": shop_executor,
    "agent": agent_executor,
}
