"""首页推荐提问服务（方案 C：规则取料 → 模板生成 → AI 润色 → Redis 缓存）

分层职责：
1. 取料层（规则）：从最近对话 + 操作日志抽取品类/预算/商品槽位，不做 NLP
2. 模板层：槽位填模板得到 6 条候选话题，同时作为 AI 失败时的兜底
3. AI 润色层（可选）：LLM 只改措辞、不允许编造话题外内容，3s 超时
4. 缓存层：Redis key home:suggestions:{user_id|anon}，TTL 2h，
   用户新建对话时由 chat_rounter 主动失效

降级链：AI 失败 → 模板文案 → 用户无历史 → 内置通用话题。
本模块任何异常都不应抛出到路由层——推荐框是装饰性功能，永远给得出结果。
"""
import asyncio
import json
import logging
import os
import re

from src.repositories.conversation_repository import ConversationRepository


logger=logging.getLogger(__name__)
LLM_POLISH_ENABLED=os.getenv("SUGGESTION_LLM_POLISH","1")!="0"
SUGGESTION_MODEL="aliyun/tongyi-xiaomi-analysis-flash"
SUGGESTION_COUNT=6
CACHE_TTL=7200 # 2 小时；create_thread 时会主动失效

CATEGORY_KEYWORDS={
   "手机": ["手机", "iphone", "华为", "小米", "oppo", "vivo", "折叠屏"],
    "笔记本电脑": ["笔记本", "laptop", "macbook", "电脑"],
    "耳机": ["耳机", "降噪", "airpods", "蓝牙耳机"],
    "扫地机器人": ["扫地机器人", "扫地机", "洗地机", "吸尘器"],
    "家电": ["家电", "冰箱", "洗衣机", "空调", "电视"],
    "相机": ["相机", "微单", "gopro", "大疆"],
    "键盘": ["键盘", "鼠标", "外设"],
}

BUDGET_RE=re.compile(r"(?:预算|¥|￥|花)\s?(\d{3,5})|(\d{3,5})\s?元(?:以内|左右|预算)?")
# 用户无任何历史时的通用话题（与前端 FALLBACK_PROMPTS 语义一致）
DEFAULT_TOPICS = [
    "帮我选 3000 元降噪耳机",
    "618 该买扫地机器人吗",
    "对比 iPhone 16 和华为 Pura 70",
    "推荐性价比笔记本电脑",
    "学生党平价手机推荐",
    "哪些家电值得囤货",
]

# {预算} {品类} {商品A} {商品B} 槽位不足的模板会被跳过
TEMPLATES = [
    "帮我选 {预算} 元{品类}",
    "推荐性价比{品类}",
    "{商品A}值得买吗",
    "对比 {商品A} 和 {商品B}",
    "618 该买{品类}吗",
    "{预算} 元以内{品类}有什么推荐",
    "学生党平价{品类}推荐",
    "哪些{品类}值得囤货",
]
async def _recent_user_messages(user_id:str,limit:int=30)->list[str]:
   """取用户最近对话里的用户侧消息文本，取不到就返回空列表"""
   try:
      from src.storage.postgres.manager import pg_manager
      pg_manager._check_initialized()
      async with pg_manager.get_async_session_context() as session:
         convs=await ConversationRepository(session).list_by_user(user_id,limit=5)
         texts:list[str]=[]
         
         for conv in convs :
            for msg in conv.messages or []:
               if msg.get("role")!="user":
                  continue
               content=msg.get("content")
               if isinstance(content,list): #多模块消息去文本类
                  content=" ".join(
                     b.get("text","") for b in content
                     if isinstance(b,dict) and b.get("type")=="text"
                  )
               if isinstance(content,str) and content.strip():
                  texts.append(content.strip())
                  if len(texts)>=limit:
                     return texts
         return texts
   except Exception as e:
      logger.warning(f"[suggestion]取最近对话失败，跳过取料: {e}")
      return []
async def extract_slots(messages:list[str])->dict:
    """从消息文本中用关键词/正则抽槽位，纯规则无 NLP"""
    slots={"品类": [], "预算": [], "商品": []}
    for text in messages:
      low=text.lower()
      for cat,words in CATEGORY_KEYWORDS.items():
         if cat not in slots["品类"] and any(w in low for w in words):
            slots["品类"].append(cat)
      m=BUDGET_RE.search(text)
      if m and (m.group(1) or m.group(2)) not in slots["预算"]:
            slots["预算"].append(m.group(1) or m.group(2))
      # 商品名：取消息里 4-12 个汉字/字母数字的连续片段当商品候选（粗糙但够用）
      for name in re.findall(r"[\u4e00-\u9fa5A-Za-z0-9 ]{4,12}", text):
         name = name.strip()
         if (
               len(name) >= 4
               and name not in slots["商品"]
               and not any(k in name.lower() for k in ["帮我", "推荐", "对比", "预算", "怎么样", "值得"])
         ):
               slots["商品"].append(name)
    return slots
def build_template_prompts(slots: dict) -> list[str]:
    """槽位填模板；槽位不够的模板跳过，最后用通用话题补齐到 6 条"""
    results: list[str] = []
    cats = slots["品类"]
    for tpl in TEMPLATES:
        if len(results) >= SUGGESTION_COUNT:
            break
        try:
            text = tpl.format(
                预算=slots["预算"][0] if slots["预算"] else "3000",
                品类=(cats[len(results) % len(cats)] if cats else "数码好物"),
                商品A=slots["商品"][0] if slots["商品"] else "看中的那款",
                商品B=slots["商品"][1] if len(slots["商品"]) > 1 else "同价位竞品",
            )
        except (KeyError, IndexError):
            continue
        if text not in results:
            results.append(text)
    for topic in DEFAULT_TOPICS:
        if len(results) >= SUGGESTION_COUNT:
            break
        if topic not in results:
            results.append(topic)
    return results[:SUGGESTION_COUNT]
_POLISH_SYSTEM = (
    "你是购物助手的文案润色器。给你一组候选提问话题和用户最近聊过的内容，"
    "把每个话题改写成更自然、更口语化的中文购物提问。"
    "规则：只能基于给定话题改写，禁止编造话题外的商品或品类；"
    f"每条不超过 20 个字；恰好输出 {SUGGESTION_COUNT} 条；"
    '只输出 JSON 数组，格式 ["...", "..."]，不要任何解释。'
)


async def polish_with_llm(topics: list[str], materials: list[str]) -> list[str] | None:
    """让 LLM 把模板话题润色得自然；失败/超时返回 None 走模板兜底"""
    if not LLM_POLISH_ENABLED:
        return None
    try:
        from src.agents.common.models import load_chat_model

        model = load_chat_model(SUGGESTION_MODEL)
        user_text = f"候选话题：{json.dumps(topics, ensure_ascii=False)}\n"
        if materials:
            user_text += f"用户最近聊过：{json.dumps(materials[:5], ensure_ascii=False)}"
        resp = await asyncio.wait_for(
            model.ainvoke([("system", _POLISH_SYSTEM), ("human", user_text)]),
            timeout=3.0,
        )
        text = resp.content if isinstance(resp.content, str) else str(resp.content)
        # 容错：截取第一个 [...] 段落，防 LLM 包裹 ```json 围栏或前后缀
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if not match:
            return None
        arr = json.loads(match.group())
        if (
            isinstance(arr, list)
            and len(arr) == SUGGESTION_COUNT
            and all(isinstance(s, str) and s.strip() for s in arr)
        ):
            return [s.strip()[:30] for s in arr]
        return None
    except Exception as e:
        logger.info(f"[suggestions] AI 润色不可用，用模板兜底: {type(e).__name__}: {e}")
        return None
def _cache_key(user_id: str | None) -> str:
    return f"home:suggestions:{user_id or 'anon'}"


async def invalidate_cache(user_id: str | None) -> None:
    """用户新建对话时调用，让下次进首页重新生成（静默容错）"""
    try:
        from src.services.redis_cache import get_redis_cache

        await get_redis_cache().delete(_cache_key(user_id))
    except Exception as e:
        logger.debug(f"[suggestions] 缓存失效失败（忽略）: {e}")


async def get_suggestions(user_id: str | None) -> list[str]:
    """对外入口：永远返回 SUGGESTION_COUNT 条字符串，永不抛异常"""
    try:
        from src.services.redis_cache import get_redis_cache

        cache = get_redis_cache()
        cached = await cache.get(_cache_key(user_id))
        if isinstance(cached, list) and cached:
            return cached
    except Exception as e:
        logger.debug(f"[suggestions] 缓存读取失败（忽略）: {e}")
        cache = None

    # 1. 取料（未登录/无历史 → 空料 → 模板层落到通用话题）
    materials = await _recent_user_messages(user_id) if user_id else []
    # 2. 模板层：保证一定有结果
    topics = build_template_prompts(extract_slots(materials)) if materials else list(DEFAULT_TOPICS)
    # 3. AI 润色：失败则 topics 原样作为结果
    prompts = await polish_with_llm(topics, materials) or topics

    if cache is not None:
        try:
            await cache.set(_cache_key(user_id), prompts, ttl=CACHE_TTL)
        except Exception as e:
            logger.debug(f"[suggestions] 缓存写入失败（忽略）: {e}")
    return prompts

