"""内置工具集 - ShoppingClaw 硬编码工具实现"""
import logging
import re
from typing import Annotated, Any, List, Optional
from pydantic import BaseModel, Field

from langgraph.types import interrupt
from sqlalchemy import select
from langchain_ollama import ChatOllama
from langchain_core.prompts import ChatPromptTemplate

from src.agents.common.toolkits import tool
from src.storage.postgres.manager import pg_manager
from src.storage.postgres.models_business import User

logger = logging.getLogger(__name__)


# ==================== 数据模型定义 ====================

class ShoppingIntent(BaseModel):
    """提取出的结构化购物意图"""
    category: Optional[str] = Field(None, description="商品品类，如'手机'、'笔记本电脑'、'耳机'")
    budget_min: Optional[float] = Field(None, description="最低预算金额")
    budget_max: Optional[float] = Field(None, description="最高预算金额")
    brands: List[str] = Field(default_factory=list, description="偏好的品牌列表")
    keywords: List[str] = Field(default_factory=list, description="核心需求关键词，如'大内存'、'控油'、'降噪'")
    urgency: str = Field("medium", description="紧迫程度，可选值为 low, medium, high")
    reasoning: Optional[str] = Field(None, description="简短的解析逻辑说明")

class TaskProgress(BaseModel):
    """购物任务执行进度"""
    stage: str = Field(..., description="当前阶段，如'需求确认', '商品搜索', '对比分析', '最终推荐'")
    completed_steps: List[str] = Field(default_factory=list, description="已完成的步骤描述")
    next_step: Optional[str] = Field(None, description="建议的下一步操作")
    status: str = Field("in_progress", description="任务状态: in_progress, completed, blocked")


# ==================== 记忆与上下文管理工具 ====================

@tool(
    category="buildin",
    tags=["画像", "上下文"],
    display_name="获取综合购物上下文",
    icon="🧠"
)
async def get_user_shopping_context(user_id: str) -> str:
    """获取当前用户的综合购物上下文，包括长期偏好、近期意图和历史决策。
    主 Agent 在开始新任务或需要深入了解用户时应首先调用此工具。
    
    参数:
        user_id: 用户ID
    """
    logger.info(f"[Tool] 获取综合购物上下文: {user_id}")
    try:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = result.scalars().first()
            
            if not user:
                return f"错误: 未找到用户 {user_id}"

            config = user.config_json or {}
            prefs = config.get("preferences", {})
            history = config.get("history", [])[-5:]  # 最近5条
            current_intent = config.get("current_intent", {})
            task_status = config.get("task_status", "idle")

            context_lines = [
                "### 用户综合购物上下文",
                f"**1. 长期偏好**: {prefs if prefs else '暂无数据'}",
                f"**2. 最近5条历史决策**: {history if history else '暂无数据'}",
                f"**3. 当前进行中的意图**: {current_intent if current_intent else '暂无'}",
                f"**4. 任务系统状态**: {task_status}",
            ]
            return "\n".join(context_lines)
    except Exception as e:
        logger.error(f"获取购物上下文失败: {e}")
        return f"获取上下文失败: {str(e)}"

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
            
            # 显式标记 JSON 字段已修改，确保 SQLAlchemy 检测到变化
            from sqlalchemy.orm import attributes
            attributes.flag_modified(user, "config_json")
            
            # commit 由 get_async_session_context 自动处理
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


# ==================== 任务管理工具 ====================

@tool(
    category="buildin",
    tags=["任务", "状态"],
    display_name="追踪任务进度",
    icon="📈"
)
async def track_task_progress(
    user_id: str, 
    stage: str, 
    step_description: str, 
    status: str = "in_progress",
    next_step: Optional[str] = None
) -> str:
    """实时追踪当前购物任务的执行进度，便于主 Agent 记录状态和断点续传。
    
    参数:
        user_id: 用户ID
        stage: 当前阶段 (如: "需求确认", "全网搜集", "对比分析", "最终推荐")
        step_description: 已完成的步骤简述
        status: 当前状态 (in_progress, completed, blocked)
        next_step: 建议的下一步操作内容
    """
    logger.info(f"[Tool] 追踪任务进度: {user_id} | {stage} | {status}")
    try:
        async with pg_manager.get_async_session_context() as session:
            result = await session.execute(select(User).where(User.user_id == user_id))
            user = result.scalars().first()
            if not user:
                return f"错误: 未找到用户 {user_id}"
            
            if not user.config_json:
                user.config_json = {}
            
            progress = user.config_json.get("task_progress", {
                "stage": "需求确认",
                "completed_steps": [],
                "status": "idle"
            })
            
            progress["stage"] = stage
            progress["status"] = status
            if step_description not in progress["completed_steps"]:
                progress["completed_steps"].append(step_description)
            if next_step:
                progress["next_step"] = next_step
                
            user.config_json["task_progress"] = progress
            user.config_json["task_status"] = f"{stage} ({status})"
            
            from sqlalchemy.orm import attributes
            attributes.flag_modified(user, "config_json")
            
        return f"✅ 任务进度已更新: {stage} - {step_description} ({status})"
    except Exception as e:
        logger.error(f"更新任务进度失败: {e}")
        return f"更新任务进度失败: {str(e)}"

@tool(
    category="buildin",
    tags=["计算", "价格"],
    display_name="价格计算器",
    icon="🧮"
)
def price_calculator(expression: str) -> str:
    """执行复杂的数学运算，特别适用于计算折扣、总价或对比价格。
    
    参数:
        expression: 数学表达式 (如: "(2999 * 0.8) + 50" 或 "5000 / 3")
    """
    try:
        # 使用安全的方式评估简单数学表达式
        # 仅允许数字和基本运算符
        if not re.match(r'^[0-9+\-*/().\s]+$', expression):
            return "错误: 表达式包含非法字符，仅支持数字和 + - * / ( )"
        
        result = eval(expression, {"__builtins__": None}, {})
        return f"计算结果: {expression} = {result:.2f}"
    except Exception as e:
        logger.error(f"Price calculator error: {e}")
        return f"计算失败: {str(e)}"


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
) -> str:
    """向用户发起问题并等待回答。

    此工具将问题格式化为自然语言文本返回。
    Agent 应将返回内容直接展示给用户，然后在下一轮对话中根据用户回答继续执行。

    注意：不要在回复中使用"让我向您提问"等暴露工具调用的表述，
    直接把问题自然呈现给用户。
    """
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

    # 格式化为自然语言问题文本
    lines = []
    for i, q in enumerate(input_questions):
        q_text = q.get("question", "")
        opts = q.get("options", [])
        multi = q.get("multi_select", False)
        allow = q.get("allow_other", True)

        if len(input_questions) > 1:
            lines.append(f"**{i+1}. {q_text}**")
        else:
            lines.append(f"{q_text}")

        if opts:
            labels = [opt.get("label", opt.get("value", str(opt))) for opt in opts]
            if multi:
                lines.append(f"（可多选：{' | '.join(labels)}）")
            else:
                lines.append(f"（{' / '.join(labels)}）")
        if allow:
            lines.append("（也可以直接告诉我你的想法）")

    return "\n\n".join(lines)


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

            prefs = {}
            history: list[dict] = []
            interests: list[str] = []

            if user.config_json:
                prefs = user.config_json.get("preferences", {})
                history = user.config_json.get("history", [])
                interests = user.config_json.get("interests", [])

            # 简单组装一段文本画像，MasterAgent 可以直接塞进 prompt
            lines = [
                "用户画像:",
                f"- 用户名: {user.user_name}",
                f"- 角色: {user.role}",
                f"- 注册时间: {user.created_at}",
                f"- 偏好: {prefs}",
                f"- 兴趣: {interests}",
                f"- 最近历史决策数: {len(history)}",
            ]
            return "\n".join(lines)
    except Exception as e:
        logger.error(f"获取用户画像失败: {e}")
        return f"获取失败: {str(e)}"







# ==================== 数据展示与格式化工具 ====================

@tool(
    category="buildin",
    tags=["展示", "格式化"],
    display_name="渲染商品卡片",
    icon="🃏"
)
def render_product_card(product: dict) -> str:
    """将商品数据渲染为精美的 Markdown 卡片。
    
    参数:
        product: 商品字典，包含 title, price, platform, url, image_url, rating, shop_name 等
    """
    logger.info(f"[Tool] 渲染商品卡片: {product.get('title', 'Unknown')}")
    
    title = product.get("title", "未知商品")
    try:
        price = float(product.get("price", 0))
    except (ValueError, TypeError):
        price = 0.0
    platform = product.get("platform", "unknown")
    url = product.get("url", "#")
    image_url = product.get("image_url")
    rating = product.get("rating")
    shop_name = product.get("shop_name", "未知店铺")
    
    platform_icons = {"jd": "🔴 京东", "taobao": "🟠 淘宝", "pdd": "🔴 拼多多"}
    p_icon = platform_icons.get(platform, "🛒 " + platform)
    
    card = [
        f"### {title}",
        f"**{p_icon}** | **{shop_name}**",
        f"---",
        f"💰 **到手价: ¥{price:.2f}**",
    ]
    
    if rating:
        card.append(f"⭐ **评分: {rating}**")
        
    card.append(f"\n[点击查看详情 >>]({url})")
    
    if image_url:
        # 使用 HTML 标签控制图片大小，适配 Streamlit
        card.append(f'\n<img src="{image_url}" width="200">')
        
    # Return structured JSON for frontend SSE interception
    import json
    return json.dumps({
        "type": "product_card",
        "data": {
            "title": title,
            "price": price,
            "platform": platform,
            "url": url,
            "image_url": image_url,
            "rating": rating,
            "shop_name": shop_name,
        }
    }, ensure_ascii=False)


@tool(
    category="buildin",
    tags=["展示", "对比"],
    display_name="格式化对比表格",
    icon="📊"
)
def format_comparison_table(products: list[dict]) -> str:
    """将多个商品格式化为专业的 Markdown 对比表格，包含价格、评分、销量及核心卖点。
    
    参数:
        products: 商品列表，每个商品应包含 title, price, platform, rating, sales_count, specs(可选) 等
    """
    logger.info(f"[Tool] 格式化对比表格: {len(products)} 个商品")
    
    if not products:
        return "没有商品可对比"
    
    # 获取所有商品的共同规格键名
    all_spec_keys = set()
    for p in products:
        if "specs" in p and isinstance(p["specs"], dict):
            all_spec_keys.update(p["specs"].keys())
    
    # 选出前3个最重要的规格字段
    important_specs = sorted(list(all_spec_keys))[:3]
    
    # 表头
    headers = ["商品", "价格", "平台", "评分", "销量"] + important_specs
    header_row = "| " + " | ".join(headers) + " |"
    separator_row = "| " + " | ".join(["---"] * len(headers)) + " |"
    
    table_lines = [header_row, separator_row]
    
    # 平台映射
    platform_names = {"jd": "京东", "taobao": "淘宝", "pdd": "拼多多"}
    
    for product in products:
        title = product.get("title", "未知")[:15] + "..." if len(product.get("title", "")) > 15 else product.get("title", "未知")
        try:
            p_price = float(product.get("price", 0))
        except (ValueError, TypeError):
            p_price = 0.0
        price = f"**¥{p_price:.2f}**"
        platform = platform_names.get(product.get("platform", ""), product.get("platform", "-"))
        rating = f"{product.get('rating', '-')}"
        sales = str(product.get('sales_count', '-'))
        
        spec_values = []
        for key in important_specs:
            spec_values.append(str(product.get("specs", {}).get(key, "-")))
            
        row = [title, price, platform, rating, sales] + spec_values
        table_lines.append("| " + " | ".join(row) + " |")
    
    return "\n".join(table_lines)
