"""内置工具集 - ShoppingClaw 硬编码工具实现"""
import logging
from typing import Annotated, Any

from langgraph.types import interrupt
from sqlalchemy import select

from src.agents.common.toolkits import tool
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import User

logger = logging.getLogger(__name__)


# ==================== 记忆与上下文管理工具 ====================

@tool(
    category="buildin",
    tags=["记忆", "偏好"],
    display_name="保存用户偏好",
    icon="💾"
)
async def save_user_preference(user_id: str, key: str, value: str) -> str:
    """将用户的长期偏好（如品牌喜好、预算范围、特殊需求）保存到记忆库。
    
    参数:
        user_id: 用户ID
        key: 偏好键名（如 "brand_preference", "max_budget"）
        value: 偏好值（如 "小米", "5000"）
    """
    logger.info(f"[Tool] 保存用户偏好: {user_id} | {key} = {value}")
    try:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = result.scalars().first()
            
            if not user:
                return f"错误: 未找到用户 {user_id}"
            
            # 更新用户配置中的偏好信息
            if not user.config_json:
                user.config_json = {}
            if "preferences" not in user.config_json:
                user.config_json["preferences"] = {}
            
            user.config_json["preferences"][key] = value
            await session.commit()
            return f"已保存偏好: {key} = {value}"
    except Exception as e:
        logger.error(f"保存偏好失败: {e}")
        return f"保存失败: {str(e)}"


@tool(
    category="buildin",
    tags=["记忆", "历史"],
    display_name="检索历史决策",
    icon="🔍"
)
async def recall_past_decisions(user_id: str, topic: str) -> str:
    """从历史决策记录中检索类似案例。当需要了解用户过去的购物选择或避免重复推荐时调用。
    
    参数:
        user_id: 用户ID
        topic: 搜索主题（如 "手机", "笔记本电脑", "耳机"）
    """
    logger.info(f"[Tool] 检索历史决策: {user_id} | {topic}")
    try:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = result.scalars().first()
            
            if not user or not user.config_json:
                return f"未找到与 '{topic}' 相关的历史决策记录"
            
            # 从 config_json 中模拟检索历史记录
            history = user.config_json.get("history", [])
            matched = [h for h in history if topic.lower() in h.get("topic", "").lower()]
            
            if matched:
                return f"找到 {len(matched)} 条与 '{topic}' 相关的历史决策: {matched[:3]}"
            return f"未找到与 '{topic}' 直接相关的历史记录，但发现以下相关兴趣: {list(user.config_json.get('interests', []))}"
    except Exception as e:
        logger.error(f"检索历史决策失败: {e}")
        return f"检索失败: {str(e)}"


# ==================== 精确计算工具 ====================

@tool(
    category="buildin",
    tags=["计算"],
    display_name="计算器",
    icon="🧮"
)
def calculator(a: float, b: float, operation: str) -> float:
    """计算器：对给定的2个数字进行基本数学运算。
    
    参数:
        a: 第一个数字
        b: 第二个数字
        operation: 运算类型 (add, subtract, multiply, divide)
    """
    try:
        if operation == "add":
            return a + b
        elif operation == "subtract":
            return a - b
        elif operation == "multiply":
            return a * b
        elif operation == "divide":
            if b == 0:
                raise ZeroDivisionError("除数不能为零")
            return a / b
        else:
            raise ValueError(f"不支持的运算类型: {operation}")
    except Exception as e:
        logger.error(f"Calculator error: {e}")
        raise


# ==================== 人机协同工具 ====================

ASK_USER_QUESTION_DESCRIPTION = """
在执行过程中，当你需要用户做决定或补充需求时，使用这个工具向用户提问。

适用场景：
1. 收集用户偏好或需求（例如风格、范围、优先级）
2. 澄清模糊指令（存在多种合理解释时）
3. 在实现过程中让用户选择方案方向
4. 在有明显权衡时让用户做取舍

使用规范：
1. questions 提供 1-5 个问题，每项包含：question, options, multi_select, allow_other
2. 每个问题的 options 提供 2-5 个有区分度的选项，每项包含 label 和 value
3. 若有推荐选项：把推荐项放在第一位，并在 label 末尾加 "(Recommended)"
4. 若需要多选：将该问题的 multi_select 设为 true
5. allow_other 通常保持 true，用户可通过 Other 输入自定义答案

注意事项：
1. 不要用这个工具询问“是否继续执行”“计划是否准备好”这类流程控制问题
2. 不要在信息已充分、无需用户决策时滥用该工具
3. 先基于现有上下文自行决策，只有关键不确定性时才提问

返回结果：
answer 为 object，格式为 {question_id: answer}。
其中 answer 可能是 string（单选）、list（多选）或 object（Other 文本）。
"""

@tool(
    category="buildin",
    tags=["交互", "中断"],
    display_name="向用户提问",
    icon="❓",
    description=ASK_USER_QUESTION_DESCRIPTION,
)
def ask_user_question(
    questions: Annotated[
        list[dict] | None,
        "问题列表，每项格式 {question, options, multi_select, allow_other, question_id(optional)}",
    ] = None,
    question: Annotated[str, "兼容字段：单个问题文本（建议优先使用 questions）"] = "",
    options: Annotated[list[dict] | None, "兼容字段：单个问题候选项（建议优先使用 questions）"] = None,
    multi_select: Annotated[bool, "兼容字段：单个问题是否允许多选"] = False,
    allow_other: Annotated[bool, "兼容字段：单个问题是否允许 Other 自定义答案"] = True,
) -> dict:
    """向用户发起问题并等待回答。"""
    input_questions = questions
    if not input_questions:
        legacy_question = str(question or "").strip()
        if legacy_question:
            input_questions = [
                {
                    "question": legacy_question,
                    "options": options or [],
                    "multi_select": multi_select,
                    "allow_other": allow_other,
                }
            ]

    if not input_questions:
        raise ValueError("questions 至少需要包含一个有效问题")

    interrupt_payload = {
        "questions": input_questions,
        "source": "ask_user_question",
    }
    answer = interrupt(interrupt_payload)

    return {
        "questions": input_questions,
        "answer": answer,
    }


# ==================== 用户画像查询工具 ====================

@tool(
    category="buildin",
    tags=["画像", "查询"],
    display_name="获取用户画像",
    icon="👤"
)
async def get_user_profile(user_id: str) -> str:
    """获取当前用户的完整画像信息（包括历史偏好、预算限制、品牌倾向等）。在开始推荐前调用，以便个性化决策。
    
    参数:
        user_id: 用户ID
    """
    logger.info(f"[Tool] 获取用户画像: {user_id}")
    try:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = result.scalars().first()
            
            if not user:
                return f"错误: 未找到用户 {user_id}"
            
            return f"""
            用户画像:
            - 用户名: {user.user_name}
            - 角色: {user.role}
            - 注册时间: {user.created_at}
            - (其他偏好信息需从关联表或 config_json 中获取)
            """
    except Exception as e:
        logger.error(f"获取用户画像失败: {e}")
        return f"获取失败: {str(e)}"
