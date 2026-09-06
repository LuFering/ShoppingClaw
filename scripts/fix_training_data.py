"""Fix training data issues without re-calling API: budget_min/max swap, missing greeting/unknown, reason extraction."""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "joint_intent", "train.jsonl")

with open(DATA_FILE, encoding="utf-8") as f:
    data = [json.loads(l) for l in f if l.strip()]

print(f"Loaded {len(data)} samples")

fixes = {"budget_swap": 0, "reason_added": 0, "greeting_added": 0, "unknown_added": 0}

# ══════════════════════════════════════════════════════════════════════
# 1. Fix budget_min <-> budget_max confusion
# ══════════════════════════════════════════════════════════════════════

# Patterns indicating the amount is a cap (max), not a floor (min)
MAX_INDICATORS = [
    r'以内', r'以下', r'不到', r'不超过', r'之内',
    r'左右', r'上下',  # ambiguous but usually max in shopping context
]

def is_budget_max_context(text: str, slot_value: str) -> bool:
    """Check if the text around the slot value suggests it's a budget_max, not min."""
    idx = text.find(slot_value)
    if idx == -1:
        return False
    after = text[idx + len(slot_value):idx + len(slot_value) + 10]
    before = text[max(0, idx - 3):idx]

    # Explicit max indicators after the number
    for pat in MAX_INDICATORS:
        if re.search(pat, after):
            return True
    # "X以内" pattern before
    if re.search(rf'{re.escape(slot_value)}\s*(元|块)?\s*(以内|以下|左右|上下|不到|不超过)', text):
        return True
    return False

def is_budget_min_context(text: str, slot_value: str) -> bool:
    """Check if text suggests budget_min."""
    idx = text.find(slot_value)
    if idx == -1:
        return False
    after = text[idx + len(slot_value):idx + len(slot_value) + 10]
    for pat in [r'以上', r'起', r'起跳', r'起步', r'不低于']:
        if re.search(pat, after):
            return True
    return False

for sample in data:
    text = sample["text"]
    for slot in sample["slots"]:
        if slot["entity"] == "budget_min":
            if is_budget_max_context(text, slot["value"]) and not is_budget_min_context(text, slot["value"]):
                slot["entity"] = "budget_max"
                fixes["budget_swap"] += 1
        elif slot["entity"] == "budget_max":
            if is_budget_min_context(text, slot["value"]) and not is_budget_max_context(text, slot["value"]):
                slot["entity"] = "budget_min"
                fixes["budget_swap"] += 1

print(f"  Budget min/max swaps: {fixes['budget_swap']}")

# ══════════════════════════════════════════════════════════════════════
# 2. Extract reason from return_request text via regex
# ══════════════════════════════════════════════════════════════════════

REASON_PATTERNS = [
    (r'(质量[不有]好[了]?|质量问题|有瑕疵|坏了|破损[了]?|损坏)', '质量问题'),
    (r'(尺码[不有]对|码数[不有]对|大小不合适|[大大小小]了|穿不[上了下进])', '尺码不合适'),
    (r'(颜色[不有]对|色差[大严重]|颜色不喜欢)', '颜色不对'),
    (r'(款式[不有]对|款式不喜欢|样式不喜欢|不好看|太丑)', '款式不喜欢'),
    (r'(发错[货物了]|型号[不有]对|版本[不有]对|寄错)', '发错货'),
    (r'(漏发|少发|少[了件]|不齐全)', '漏发'),
    (r'(没收到|未收到|没到货|还没到)', '没收到'),
    (r'([与跟]描述不符|[跟和]图片不一样|虚假宣传|实物不符)', '与描述不符'),
    (r'(假货|仿冒|非正品|冒牌|假[的了])', '疑似假货'),
    (r'(不满意|不喜欢|不想要了|后悔了|买错[了]|拍错[了])', '不满意'),
    (r'(坏了|不能用|不好用|用不了|有问题)', '商品有问题'),
]

for sample in data:
    if sample["sub_intent"] != "return_request":
        continue
    if any(s["entity"] == "reason" for s in sample["slots"]):
        continue

    text = sample["text"]
    for pattern, label in REASON_PATTERNS:
        m = re.search(pattern, text)
        if m:
            # Check no existing slot overlaps this region
            overlap = False
            for s in sample["slots"]:
                if not (m.end() <= s["start"] or m.start() >= s["end"]):
                    overlap = True
                    break
            if not overlap:
                sample["slots"].append({
                    "entity": "reason",
                    "start": m.start(),
                    "end": m.end(),
                    "value": m.group(1)
                })
                fixes["reason_added"] += 1
                break

print(f"  Reasons added: {fixes['reason_added']}")

# ══════════════════════════════════════════════════════════════════════
# 3. Add templated greeting samples (no API needed)
# ══════════════════════════════════════════════════════════════════════

GREETING_TEMPLATES = [
    "你好", "你好呀", "您好", "嗨", "hi", "hello", "哈喽", "哈咯",
    "在吗", "在不在", "在不在线", "有人在吗", "有人在吗请问",
    "谢谢", "谢谢你", "多谢", "感谢", "谢谢啦", "感谢你",
    "你是谁", "你叫什么", "你叫什么名字", "你是谁呀", "请问你是谁",
    "你能做什么", "你会什么", "你有什么功能", "你会哪些功能", "你能帮我做什么",
    "早上好", "下午好", "晚上好", "中午好", "早啊", "早", "晚安",
    "再见", "拜拜", "回头见", "下次见", "bye", "bye bye",
    "好的谢谢", "OK", "ok", "嗯嗯", "好的", "行", "明白了谢谢",
    "请问", "想问你一下", "咨询一下", "打扰一下", "麻烦问一下",
    "嘿", "喂", "在忙吗", "有空吗", "在不在呀",
    "你好，请问", "你好在吗", "您好打扰了",
    "请问能帮我吗", "可以帮我吗", "帮我个忙",
    "你好我想请问一下", "在吗想问你个事",
    "你是机器人吗", "你是AI吗", "你是真人吗", "你是人工智能吗",
    "你会说中文吗", "你支持中文吗",
]

# Deduplicate against existing
existing_texts = {d["text"] for d in data}
added = 0
for tmpl in GREETING_TEMPLATES:
    if tmpl not in existing_texts:
        data.append({
            "text": tmpl,
            "main_intent": "greeting",
            "sub_intent": "none",
            "slots": []
        })
        existing_texts.add(tmpl)
        added += 1
fixes["greeting_added"] = added
print(f"  Greetings added: {added}")

# ══════════════════════════════════════════════════════════════════════
# 4. Add templated unknown samples
# ══════════════════════════════════════════════════════════════════════

UNKNOWN_TEMPLATES = [
    "今天天气怎么样", "明天天气", "天气预报", "今天会下雨吗", "这周天气",
    "讲个笑话", "讲个冷笑话", "讲个段子", "来段脱口秀",
    "现在几点", "几点了", "今天几号", "今天是星期几", "现在什么时间",
    "帮我查查北京天气", "上海天气怎么样", "深圳今天热吗",
    "搜一下周杰伦是谁", "李白是哪个朝代的", "中国有多少人口",
    "帮我翻译这段英文", "翻译一下hello world", "这个英文什么意思",
    "有什么好玩的游戏", "推荐一部电影", "最近有什么好看的剧",
    "1+1等于几", "100乘以50是多少", "算一下356除以7",
    "明天会下雨吗", "后天天气如何", "下周天气预报",
    "周杰伦是谁", "马云是谁", "特斯拉是什么",
    "帮我写首诗", "写个作文", "写一段代码",
    "你会讲笑话吗", "唱首歌", "放个音乐",
    "有什么新闻", "今天头条", "最新消息",
    "我想聊天", "陪我聊会天", "好无聊",
    "你会下棋吗", "玩游戏吗", "斗地主",
    "帮我查个词", "成语接龙", "猜谜语",
    "世界上最高的山是什么", "地球到月球多远",
    "怎么健身", "如何减肥", "怎么学英语",
    "今天心情不好", "好烦啊", "无聊死了",
    "这个字怎么读", "嫑是什么意思", "帮我写个请假条",
    "教我做饭", "红烧肉怎么做", "鸡蛋怎么煮",
    "深蹲怎么做", "平板支撑标准姿势", "怎么练腹肌",
]

added = 0
for tmpl in UNKNOWN_TEMPLATES:
    if tmpl not in existing_texts:
        data.append({
            "text": tmpl,
            "main_intent": "unknown",
            "sub_intent": "none",
            "slots": []
        })
        existing_texts.add(tmpl)
        added += 1
fixes["unknown_added"] = added
print(f"  Unknown added: {added}")

# ══════════════════════════════════════════════════════════════════════
# 5. Validate and sort slots
# ══════════════════════════════════════════════════════════════════════

VALID_ENTITIES = {"category", "brand", "budget_max", "budget_min", "product_a", "product_b", "order_id", "reason", "issue_type"}

for sample in data:
    valid_slots = []
    for s in sample.get("slots", []):
        if s["entity"] not in VALID_ENTITIES:
            continue
        if not (0 <= s["start"] < s["end"] <= len(sample["text"])):
            continue
        if sample["text"][s["start"]:s["end"]] != s["value"]:
            real_start = sample["text"].find(s["value"], max(0, s["start"] - 5))
            if real_start != -1:
                s["start"] = real_start
                s["end"] = real_start + len(s["value"])
            else:
                continue
        valid_slots.append(s)
    valid_slots.sort(key=lambda x: (x["start"], x["end"]))
    sample["slots"] = valid_slots

# ══════════════════════════════════════════════════════════════════════
# Save
# ══════════════════════════════════════════════════════════════════════

with open(DATA_FILE, "w", encoding="utf-8") as f:
    for sample in data:
        f.write(json.dumps(sample, ensure_ascii=False) + "\n")

print(f"\n{'='*50}")
print(f"Saved {len(data)} samples to {DATA_FILE}")
print(f"Fixes applied: {fixes}")
print(f"{'='*50}")
