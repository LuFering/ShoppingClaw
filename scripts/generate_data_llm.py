import json
import os
import time
import re
import requests

from dotenv import load_dotenv
load_dotenv()


api_key=os.getenv("DEEPSEEK_API_KEY")

# DeepSeek API (OpenAI-compatible)
API_URL = "https://api.deepseek.com/v1/chat/completions"


# ══════════════════════════════════════════════════════════════════════
# Slot annotation - LLM-based with regex fallback
# ══════════════════════════════════════════════════════════════════════

# Valid entity types from intent_schema.py
VALID_ENTITIES = {
    "category", "brand", "budget_max", "budget_min",
    "product_a", "product_b", "order_id", "reason", "issue_type"
}

# Entity definitions per intent for annotation guidance
INTENT_ENTITIES = {
    ("product_recommend", "single_product"): ["category", "brand", "budget_max", "budget_min"],
    ("product_recommend", "multi_compare"): ["category", "brand", "budget_max", "budget_min"],
    ("product_comparison", "direct_compare"): ["product_a", "product_b"],
    ("product_comparison", "category_compare"): ["category", "brand"],
    ("order_query", "status_check"): ["order_id"],
    ("order_query", "logistics_track"): ["order_id"],
    ("after_sales", "return_request"): ["order_id", "reason"],
    ("after_sales", "repair_request"): ["order_id", "issue_type"],
    ("price_check", "none"): ["category", "brand"],
    ("store_search", "none"): ["brand"],
    ("greeting", "none"): [],
    ("unknown", "none"): [],
}

# Expanded regex fallback (much wider coverage than original)
REGEX_PATTERNS_FALLBACK = {
    'category': [
        # 数码3C
        r'(手机|智能手机|5G手机|折叠屏|游戏手机|拍照手机)',
        r'(笔记本|笔记本电脑|游戏本|轻薄本|商务本|全能本|上网本|MacBook)',
        r'(电脑|台式机|一体机|主机|组装机)',
        r'(平板|平板电脑|iPad|学习平板)',
        r'(耳机|蓝牙耳机|无线耳机|降噪耳机|头戴耳机|入耳式|骨传导|TWS)',
        r'(音箱|音响|蓝牙音箱|智能音箱|Soundbar|回音壁)',
        r'(手表|智能手表|运动手表|机械表|石英表|电子表|儿童手表)',
        r'(手环|智能手环|运动手环|健康手环)',
        r'(显示器|显示屏|电竞显示器|4K显示器|带鱼屏|便携显示器)',
        r'(相机|微单|单反|卡片机|运动相机|拍立得|无人机)',
        r'(键盘|机械键盘|薄膜键盘|鼠标|电竞鼠标|充电器|充电宝|移动电源|数据线)',
        # 家电
        r'(电视|电视机|智能电视|OLED电视|投影仪|激光电视)',
        r'(空调|挂机|柜机|中央空调|变频空调|移动空调)',
        r'(冰箱|对开门|十字门|法式门|冰柜|车载冰箱)',
        r'(洗衣机|烘干机|洗烘一体|滚筒|波轮|迷你洗衣机)',
        r'(电饭煲|电压力锅|微波炉|空气炸锅|烤箱|电磁炉|破壁机|豆浆机|咖啡机|净水器|扫地机器人|吸尘器|除螨仪|加湿器|取暖器|电风扇)',
        # 服饰美妆
        r'(西装|西服|衬衫|领带|休闲裤|牛仔裤|运动裤|短裤|T恤|卫衣|夹克|羽绒服|冲锋衣|运动鞋|跑鞋|篮球鞋|板鞋|帆布鞋|皮鞋|高跟鞋|凉鞋|拖鞋|连衣裙|裙子|半身裙|风衣|大衣|防晒衣|泳衣|内衣|袜子)',
        r'(口红|唇釉|粉底|气垫|BB霜|遮瑕|眼影|腮红|眉笔|睫毛膏|卸妆|洗面奶|精华|面霜|乳液|防晒|面膜|香水|洗发水|沐浴露)',
        # 母婴
        r'(婴儿车|推车|安全座椅|婴儿床|纸尿裤|奶瓶|奶粉|吸奶器|辅食机|爬行垫|婴儿澡盆|婴儿衣服|童装|童鞋|书包|早教机|儿童手表|玩具|积木|乐高|毛绒玩具|遥控车|无人机玩具|滑板车|自行车|平衡车)',
        # 家居
        r'(沙发|茶几|电视柜|餐桌|餐椅|床|床垫|衣柜|书桌|办公桌|人体工学椅|电竞椅|收纳柜|鞋柜|窗帘|地毯|四件套|被芯|枕头|凉席|蚊帐|台灯|落地灯|吸顶灯|晾衣架|梯子|工具箱)',
        # 食品生鲜
        r'(牛奶|酸奶|坚果|零食|巧克力|饼干|方便面|螺蛳粉|茶叶|咖啡|蜂蜜|燕窝|保健品|蛋白粉|大闸蟹|牛排|三文鱼|车厘子|榴莲|草莓|蓝莓)',
        # 运动户外
        r'(跑步机|动感单车|椭圆机|哑铃|瑜伽垫|筋膜枪|羽毛球拍|网球拍|篮球|足球|帐篷|睡袋|登山杖|钓竿|滑板|轮滑鞋|望远镜)',
    ],
    'brand': [
        # 数码
        r'(华为|荣耀|小米|红米|OPPO|vivo|iQOO|一加|真我|三星|苹果|Apple|联想|ThinkPad|拯救者|小新|Yoga|戴尔|惠普|暗影精灵|华硕|ROG|宏碁|微软|Surface|雷蛇|外星人|神舟|机械革命|微星|技嘉)',
        r'(索尼|佳能|尼康|富士|松下|理光|大疆|GoPro|Bose|森海塞尔|铁三角|拜亚动力|AKG|JBL|马歇尔|哈曼卡顿|B&O|韶音|漫步者|小米|华为|OPPO|vivo|三星)',
        # 家电
        r'(格力|美的|海尔|海信|TCL|创维|长虹|小米|松下|西门子|博世|三星|LG|大金|三菱|日立|夏普|飞利浦|戴森|科沃斯|石头|追觅|云鲸|必胜|鲨客|小狗)',
        # 服饰运动
        r'(耐克|Nike|阿迪达斯|Adidas|李宁|安踏|特步|匹克|鸿星尔克|New\s?Balance|匡威|万斯|斯凯奇|亚瑟士|Onitsuka\s?Tiger|安德玛|斐乐|始祖鸟|北面|哥伦比亚|优衣库|ZARA|H&M|GAP|Levi\'s|Lee|杰克琼斯|海澜之家|七匹狼|太平鸟|波司登|雅戈尔)',
        # 美妆母婴
        r'(兰蔻|雅诗兰黛|迪奥|香奈儿|圣罗兰|阿玛尼|MAC|植村秀|资生堂|SK[-]?II|欧莱雅|OLAY|珀莱雅|薇诺娜|花西子|完美日记|珂拉琪|贝亲|好孩子|Babycare|全棉时代|可优比|小龙哈彼|惠氏|美赞臣|爱他美|飞鹤|君乐宝)',
    ],
    'budget_max': [
        r'预算(\d{3,6})',
        r'(\d{3,6})元?以内',
        r'(\d{3,6})元?左右',
        r'(\d{3,6})元?以下',
        r'(\d{3,6})块[钱左右以内]?',
        r'不超过(\d{3,6})',
        r'(\d{3,6})之内',
        r'[预价]算?[在要]?(\d{3,6})',
        r'(\d{3,6})上下',
    ],
    'budget_min': [
        r'(\d{3,6})元?以上',
        r'(\d{3,6})元?起[步跳]?',
        r'不低于(\d{3,6})',
    ],
    'order_id': [
        r'(SO_\d+)',
        r'订单号?[：:\s]*(\d{6,20})',
        r'(JD\d{10,18})',
        r'(\d{15,20})',
    ],
    'issue_type': [
        r'(屏幕碎[了坏裂]|不制冷|不制热|不加热|开不了机|无法开机|死机|重启|卡顿|闪退|无法[连联]网|WiFi.?[连联]不上|蓝牙[连联]不上|充不了电|不进电|耗电快|电池不耐用|漏[水电油气]|异响|噪音大|漏水|漏油|按键失灵|触屏失灵|指纹失灵|系统崩溃|蓝屏|花屏|黑屏|无法识别|显示异常|报错|报警|故障码|自动关机|脱落|断裂|掉色|褪色|起球|缩水|变形|异味)',
    ],
    'reason': [
        r'(质量[不有]好[了]?|质量问题|瑕疵|损坏|坏了|破了|不能用|用不了|不好用|不满意|不喜欢|不合适|不合适了|不想要了|买错了|拍错了|重复了|尺码[不有]对|码数[不有]对|大小不合适|颜色[不有]对|款式[不有]对|发错[货物了]|型号[不有]对|版本[不有]对|漏发|少发|没收到|与[描图]述不符|跟图片不一样|假货|仿冒|非正品|冒牌)',
    ],
    'product_a': [
        r'(iPhone\s?\d{1,2}\s?(Pro|Pro\s?Max|Plus|mini)?|iPad\s?(Pro|Air|mini)?\s?\d{0,2}|MacBook\s?(Pro|Air)?\s?(M\d)?|AirPods\s?(Pro|Max)?)',
        r'(华为\s?(Mate|P|nova|畅享)\s?\d{0,2}\s?(Pro|Pro\+|Ultra|RS)?|荣耀\s?\d{0,3}\s?(Pro|GT)?|小米\s?\d{1,2}\s?(Pro|Ultra|S)?|红米\s?(K|Note|Turbo)?\s?\d{0,2})',
        r'(OPPO\s?(Find|Reno)\s?\d{0,2}\s?(Pro|Pro\+)?|vivo\s?(X|S)\s?\d{0,3}\s?(Pro|Pro\+)?|一加\s?\d{1,2}\s?(Pro|T|R)?|三星\s?(Galaxy\s?)?(S|Z|A)\s?\d{0,2}\s?(Ultra|Fold|Flip)?)',
        r'(RTX\s?\d{4}\s?(Ti|SUPER)?|GTX\s?\d{3,4}|RX\s?\d{4}\s?(XT)?|Arc\s?A\d{3})',
        r'(索尼\s?(PS|Xperia|WH|WF)\s?\d{0,4}|佳能\s?(EOS\s?)?\w?\d{1,3}\s?Mark\s?\w?|大疆\s?(Mavic|Air|Mini|Phantom|Osmo)\s?\d?\s?(Pro)?)',
    ],
    'product_b': [
        r'(iPhone\s?\d{1,2}\s?(Pro|Pro\s?Max|Plus|mini)?|iPad\s?(Pro|Air|mini)?\s?\d{0,2}|MacBook\s?(Pro|Air)?\s?(M\d)?|AirPods\s?(Pro|Max)?)',
        r'(华为\s?(Mate|P|nova|畅享)\s?\d{0,2}\s?(Pro|Pro\+|Ultra|RS)?|荣耀\s?\d{0,3}\s?(Pro|GT)?|小米\s?\d{1,2}\s?(Pro|Ultra|S)?|红米\s?(K|Note|Turbo)?\s?\d{0,2})',
        r'(OPPO\s?(Find|Reno)\s?\d{0,2}\s?(Pro|Pro\+)?|vivo\s?(X|S)\s?\d{0,3}\s?(Pro|Pro\+)?|一加\s?\d{1,2}\s?(Pro|T|R)?|三星\s?(Galaxy\s?)?(S|Z|A)\s?\d{0,2}\s?(Ultra|Fold|Flip)?)',
        r'(RTX\s?\d{4}\s?(Ti|SUPER)?|GTX\s?\d{3,4}|RX\s?\d{4}\s?(XT)?|Arc\s?A\d{3})',
    ],
}


def regex_annotate_slots(text: str) -> list:
    """Regex-based slot annotation (fallback when LLM annotation fails)"""
    slots = []
    for entity_type, patterns_list in REGEX_PATTERNS_FALLBACK.items():
        for pattern in patterns_list:
            for match in re.finditer(pattern, text):
                # Avoid overlap
                overlap = any(
                    not (match.end() <= s['start'] or match.start() >= s['end'])
                    for s in slots
                )
                if not overlap:
                    value = match.group(1) if match.lastindex else match.group(0)
                    slots.append({
                        'entity': entity_type,
                        'start': match.start(),
                        'end': match.end(),
                        'value': value
                    })
    slots.sort(key=lambda x: x['start'])
    return slots


def parse_annotated_text(annotated: str) -> tuple[str, list[dict]]:
    """Parse [entity_type:value] markers from LLM output into clean text + slots.

    Example input:  '想买个[category:游戏本]，预算[budget_max:8000]左右'
    Returns: ('想买个游戏本，预算8000左右', [{entity:'category', start:3, end:6, value:'游戏本'}, ...])
    """
    pattern = re.compile(r'\[([a-z_]+):([^\]]+)\]')
    clean_text = ""
    slots = []
    last_end = 0

    for match in pattern.finditer(annotated):
        entity_type = match.group(1)
        value = match.group(2)

        if entity_type not in VALID_ENTITIES:
            clean_text += annotated[last_end:match.end()]
            last_end = match.end()
            continue

        clean_text += annotated[last_end:match.start()]
        start = len(clean_text)
        clean_text += value
        end = len(clean_text)

        slots.append({
            "entity": entity_type,
            "start": start,
            "end": end,
            "value": value
        })
        last_end = match.end()

    clean_text += annotated[last_end:]

    # Validate: deduplicate overlapping slots (keep first)
    slots.sort(key=lambda x: (x['start'], x['end']))
    filtered = []
    for s in slots:
        if any(
            not (s['end'] <= fs['start'] or s['start'] >= fs['end'])
            for fs in filtered
        ):
            continue
        if s['start'] < s['end'] <= len(clean_text):
            filtered.append(s)
    return clean_text, filtered


def llm_annotate_slots(text: str, main_intent: str, sub_intent: str, api_key: str) -> list:
    """Use DashScope LLM to annotate slots in a single text (few-shot)."""
    valid_entities = INTENT_ENTITIES.get((main_intent, sub_intent), list(VALID_ENTITIES))
    if not valid_entities:
        return []

    entity_desc = "\n".join(f"- {e}" for e in valid_entities)

    fewshot_examples = {
        ("product_recommend", "single_product"): [
            ("想买个[category:游戏本]预算[budget_max:8000]左右主要玩3A大作",
             [{"entity":"category","start":3,"end":6,"value":"游戏本"},{"entity":"budget_max","start":7,"end":11,"value":"8000"}]),
            ("[brand:华为]的[category:手机]有什么推荐的",
             [{"entity":"brand","start":0,"end":2,"value":"华为"},{"entity":"category","start":3,"end":5,"value":"手机"}]),
        ],
        ("product_recommend", "multi_compare"): [
            ("[category:手机]预算[budget_min:3000]到[budget_max:5000]推荐几款对比",
             [{"entity":"category","start":0,"end":2,"value":"手机"},{"entity":"budget_min","start":4,"end":8,"value":"3000"},{"entity":"budget_max","start":9,"end":13,"value":"5000"}]),
        ],
        ("product_comparison", "direct_compare"): [
            ("[product_a:iPhone 15]和[product_b:小米14]哪个好",
             [{"entity":"product_a","start":0,"end":10,"value":"iPhone 15"},{"entity":"product_b","start":11,"end":15,"value":"小米14"}]),
        ],
        ("product_comparison", "category_compare"): [
            ("[category:变频空调]和[category:定频空调]哪个省电",
             [{"entity":"category","start":0,"end":4,"value":"变频空调"},{"entity":"category","start":5,"end":9,"value":"定频空调"}]),
        ],
        ("order_query", "status_check"): [
            ("订单[order_id:SO_12345]现在发货了吗",
             [{"entity":"order_id","start":2,"end":10,"value":"SO_12345"}]),
        ],
        ("after_sales", "return_request"): [
            ("[order_id:123456789]这个订单想退货[reason:尺码不合适]",
             [{"entity":"order_id","start":0,"end":9,"value":"123456789"},{"entity":"reason","start":14,"end":19,"value":"尺码不合适"}]),
        ],
        ("after_sales", "repair_request"): [
            ("我的[category:手机][issue_type:屏幕碎了]能修吗",
             [{"entity":"category","start":2,"end":4,"value":"手机"},{"entity":"issue_type","start":4,"end":8,"value":"屏幕碎了"}]),
        ],
        ("price_check", "none"): [
            ("[category:手机]什么时候买最便宜",
             [{"entity":"category","start":0,"end":2,"value":"手机"}]),
        ],
        ("store_search", "none"): [
            ("附近有[brand:华为]专卖店吗",
             [{"entity":"brand","start":3,"end":5,"value":"华为"}]),
        ],
    }

    examples = fewshot_examples.get(
        (main_intent, sub_intent),
        [("[brand:小米][category:耳机]推荐", [{"entity":"brand","start":0,"end":2,"value":"小米"},{"entity":"category","start":2,"end":4,"value":"耳机"}])]
    )

    example_lines = []
    for ex_text, ex_slots in examples:
        example_lines.append(f"文本：{ex_text}")
        example_lines.append(f"标注：{json.dumps(ex_slots, ensure_ascii=False)}")
        example_lines.append("")

    prompt = f"""你是电商购物query的槽位标注专家。请在文本中用[实体类型:值]的格式标注实体。

## 需要标注的实体类型：
{entity_desc}

## 标注规则：
1. 只标注显式出现的实体，不要推测或补充
2. 用 [实体名:原文内容] 格式包裹实体，不要改变原文文字
3. 实体之间不重叠
4. 如果没有可标注的实体，原样返回文本

## 示例：
{chr(10).join(example_lines)}

## 任务：
文本：{text}
主意图：{main_intent}
子意图：{sub_intent}

请输出标注后的文本（只输出一行，不要解释）："""

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    payload = {
        "model": "DeepSeek-V4-Pro ",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 256
    }

    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        result = response.json()
        annotated = result["choices"][0]["message"]["content"].strip()
        clean, slots = parse_annotated_text(annotated)
        # Verify clean text matches original (allow whitespace differences)
        if clean.replace(" ", "") != text.replace(" ", ""):
            # LLM may have modified text, fall back to regex
            print(f"    ⚠️ LLM标注结果文本不匹配，使用正则标注")
            return regex_annotate_slots(text)
        return slots
    except Exception as e:
        print(f"    ⚠️ LLM标注失败 ({type(e).__name__}), 使用正则标注")
        return regex_annotate_slots(text)


def auto_annotate_slots(text: str, intent_type: str, sub_intent: str) -> list:
    """Annotate slots using LLM (primary) with regex fallback."""
    if api_key:
        slots = llm_annotate_slots(text, intent_type, sub_intent, api_key)
        if slots:
            return slots
    return regex_annotate_slots(text)


def _build_scenario_guide(intent_type: str, sub_intent: str) -> str:
    """Build expanded scenario guide with diverse expression styles."""

    valid_entities = INTENT_ENTITIES.get((intent_type, sub_intent), [])

    guides = {
        ("product_recommend", "single_product"): f"""
用户需要推荐单个商品。可标注实体：{valid_entities}

品类覆盖：数码3C、家电、服饰美妆、母婴、家居、运动户外、食品生鲜
场景示例：
- "想买个游戏本，预算8000左右，主要玩3A大作"
- "新家装修，客厅要买台75寸电视，画质好点的"
- "面试穿，想买套西装，1000以内"
- "宝宝快出生了，买个婴儿车，轻便好折叠的"
- "有没有控油好的洗发水，头发一天就油"
- "想入手一款通勤用的无线耳机，戴着舒服的"
- "学生党，帮我找个便宜的平板做笔记用"

表达多样性要求：
- 口语化：整一个、搞台、弄个、帮我挑、推荐下、给个建议
- 省略句：5000以内的手机、降噪耳机推荐、办公笔记本
- 疑问句：有没有...？什么...比较好？...怎么样？...行不行？
- 模糊预算：不要太贵、便宜的、性价比高、千元机、百元内
- 可含错别字/口语：华维、平果、pingguo、爱凤
""",
        ("product_recommend", "multi_compare"): f"""
用户需要在多个维度对比后推荐。可标注实体：{valid_entities}

场景示例：
- "预算5000，推荐最值得买的手机"
- "想买无线耳机，降噪要好，主要通勤用，预算500内"
- "两千内的机械键盘，打游戏用，选哪个"

表达多样性：同上，加上"帮我横评"、"几款里哪个好"、"挑一个"、"选哪款"
""",
        ("product_comparison", "direct_compare"): f"""
用户指定两个商品对比。可标注实体：{valid_entities}

场景示例：
- "iPhone 15和小米14哪个好"
- "RTX4060和4070差多少"
- "华为Mate70和三星S25怎么选"
- "AirPods Pro和索尼降噪豆推荐哪个"
- "MacBook Pro和ThinkPad X1买哪个"

表达多样性：对比一下/哪个好/差多少/选哪个/值得多花钱吗/性价比谁高
""",
        ("product_comparison", "category_compare"): f"""
品类内对比不同型号或品牌。可标注实体：{valid_entities}

场景示例：
- "变频空调和定频空调哪个省电"
- "OLED电视和MiniLED电视怎么选"
- "纯电车和混动车哪个划算"
- "电动牙刷和普通牙刷哪个好"

表达多样性：A和B的区别/哪种更.../买哪种/有什么不同
""",
        ("order_query", "status_check"): f"""
用户查询订单状态。可标注实体：{valid_entities}

场景示例：
- "订单SO_12345到哪了"
- "我昨天买的衣服发货了吗"
- "查一下订单123456789的状态"
- "JD1234567890发了吗"

表达多样性：发货了没/到哪了/什么时候到/还没发货/催一下/帮我查
""",
        ("order_query", "logistics_track"): f"""
用户追踪物流。可标注实体：{valid_entities}

场景示例：
- "我的快递到哪了"
- "物流怎么三天没更新了"
- "快递显示签收但我没收到"
- "帮忙查下快递单号YT123456"

表达多样性：到哪了/卡住了/不动了/怎么还没到/派送中/丢了
""",
        ("after_sales", "return_request"): f"""
用户咨询退货。可标注实体：{valid_entities}

场景示例：
- "这个能退货吗"
- "买了三天发现不合适能退吗"
- "想退订单123456789，尺码不对"
- "订单SO_12345质量有问题想退货"

表达多样性：退货/退款/能退吗/七天无理由/退换货/寄回去
""",
        ("after_sales", "repair_request"): f"""
用户咨询维修售后。可标注实体：{valid_entities}

场景示例：
- "手机屏幕碎了能修吗"
- "空调不制冷了怎么办"
- "耳机一边不响了保修吗"
- "笔记本开不了机，还在保修期内"

表达多样性：能修吗/保修吗/换一个/修一下多少钱/能换新吗
""",
        ("price_check", "none"): f"""
价格咨询/促销时机查询。可标注实体：{valid_entities}
**严禁标注budget_max/budget_min**

场景示例：
- "这个商品现在买值不值"
- "什么时候买最便宜"
- "双11会降价吗"
- "618买手机划算吗"
- "最近有什么优惠活动"
- "这个价格是不是先涨后降的"

表达多样性：值得吗/划算吗/什么时候降价/最低价/历史最低/有券吗
""",
        ("store_search", "none"): f"""
搜索线下门店位置。可标注实体：{valid_entities}
**严禁标注budget_max/budget_min**

场景示例：
- "附近有华为专卖店吗"
- "北京苹果直营店在哪里"
- "上海哪里有耐克门店"
- "小米之家营业时间"
- "这个牌子有实体店吗"

表达多样性：在哪/怎么去/附近/门店/专卖店/直营店/体验店
""",
        ("greeting", "none"): """
纯问候/寒暄，无购物需求，slots必须为空。
场景：你好、在吗、谢谢、你是谁、你会什么、hello、hi
""",
        ("unknown", "none"): """
无法识别意图，无购物需求，slots必须为空。
场景：今天天气怎么样、讲个笑话、现在几点、搜一下XX是谁、帮我翻译
""",
    }

    return guides.get((intent_type, sub_intent), f"""意图={intent_type}, 子意图={sub_intent}，可标注实体={valid_entities}。

场景示例：
- 品类：category（商品品类），品牌：brand（品牌名）
- 预算：budget_max（上限），budget_min（下限）
- 比较对象：product_a，product_b
- 订单售后：order_id，reason（原因），issue_type（故障）""")


def generate_samples(intent_type: str, sub_intent: str, count: int) -> list:
    """Generate annotated training samples via LLM with embedded entity markers.

    Uses [entity_type:value] format so the LLM outputs both text and slot
    annotations in a single call.  The markers are parsed out to produce
    clean text + structured slot lists.
    """
    guide = _build_scenario_guide(intent_type, sub_intent)
    valid_entities = INTENT_ENTITIES.get((intent_type, sub_intent), [])
    entity_desc = "、".join(valid_entities) if valid_entities else "无（slots必须为空数组）"

    import random, time
    random_seed = int(time.time() * 1000) % 10000

    prompt = f"""你是电商购物query生成与标注专家。请生成{count}条用户query，用 [entity_type:value] 格式直接在文本中标注实体。

## 任务
- 主意图：{intent_type}
- 子意图：{sub_intent}
- 可标注实体类型：{entity_desc}
- 随机种子：{random_seed}

## 场景参考
{guide}

## 标注格式
用 [实体名:原文文字] 包裹实体，例如：
- 想买个[category:游戏本]预算[budget_max:8000]左右
- [brand:华为][category:手机]推荐哪款
- [product_a:iPhone 15]和[product_b:小米14]对比
- 订单[order_id:SO_12345]到哪了

## 规则
1. 只标注原文中明确出现的实体，不要推测或补充
2. [实体名:原文内容] 必须严格使用原文，不要修改文字
3. 实体之间不重叠、不嵌套
4. 如果该意图不应该有槽位则不加任何标注
5. 每条一行，纯文本输出，不要编号、不要JSON

## 输出多样化要求
- 品类覆盖：数码、家电、服饰、美妆、母婴、家居、运动、食品
- 品牌多样化：华为小米苹果三星联想戴尔华硕索尼佳能格力美的海尔耐克阿迪李宁安踏优衣库兰蔻欧莱雅等
- 表达风格：口语化/省略句/疑问句/含错别字/极短查询/长句描述
- 长度：5-35字

请直接输出{count}行："""

    print(f"  📡 生成 (deepseek-chat, {count}条)...")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "deepseek-chat",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.8,
        "max_tokens": 1024
    }

    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        result = response.json()
    except requests.exceptions.Timeout:
        print(f"  ❌ API超时")
        return []
    except Exception as e:
        print(f"  ❌ API调用失败: {type(e).__name__}: {str(e)[:100]}")
        return []

    try:
        content = result["choices"][0]["message"]["content"].strip()
        # Strip markdown fences
        if content.startswith("```"):
            content = content.split('\n', 1)[1]
        if content.endswith("```"):
            content = content.rsplit('\n', 1)[0]
        content = content.strip()

        lines = [l.strip() for l in content.split('\n') if l.strip()]
        lines = [l for l in lines if not l.startswith('#') and not l.startswith('//')]

        samples = []
        for line in lines:
            # Parse annotated text → clean text + slots
            clean_text, slots = parse_annotated_text(line)

            # Filter invalid
            if len(clean_text) < 4 or len(clean_text) > MAX_TEXT_LENGTH:
                continue

            # Validate: slots must be within text bounds
            valid_slots = []
            for s in slots:
                if s["entity"] not in VALID_ENTITIES:
                    continue
                if 0 <= s["start"] < s["end"] <= len(clean_text):
                    actual = clean_text[s["start"]:s["end"]]
                    if actual == s["value"]:
                        valid_slots.append(s)
                    else:
                        # Auto-correct end position
                        corrected = clean_text.find(s["value"], s["start"])
                        if corrected != -1:
                            s["start"] = corrected
                            s["end"] = corrected + len(s["value"])
                            valid_slots.append(s)

            samples.append({
                "text": clean_text,
                "main_intent": intent_type,
                "sub_intent": sub_intent,
                "slots": valid_slots[:MAX_SLOTS_PER_SAMPLE]
            })

        return samples
    except Exception as e:
        print(f"  ❌ {intent_type}/{sub_intent}: 解析失败 - {e}")
        return []


# ══════════════════════════════════════════════════════════════════════
# Generation config
# ══════════════════════════════════════════════════════════════════════

INTENT_SUBINTENT_MAP = {
    "product_recommend": ["single_product", "multi_compare"],
    "product_comparison": ["direct_compare", "category_compare"],
    "order_query": ["status_check", "logistics_track"],
    "after_sales": ["return_request", "repair_request"],
    "price_check": ["none"],
    "store_search": ["none"],
    "greeting": ["none"],
    "unknown": ["none"]
}

# Per-intent sample targets (higher priority intents get more data)
INTENT_SAMPLE_TARGETS = {
    ("product_recommend", "single_product"): 500,
    ("product_recommend", "multi_compare"): 400,
    ("product_comparison", "direct_compare"): 300,
    ("product_comparison", "category_compare"): 300,
    ("order_query", "status_check"): 250,
    ("order_query", "logistics_track"): 250,
    ("after_sales", "return_request"): 250,
    ("after_sales", "repair_request"): 250,
    ("price_check", "none"): 200,
    ("store_search", "none"): 200,
    ("greeting", "none"): 150,
    ("unknown", "none"): 150,
}

SAMPLES_PER_BATCH = 10       # Per API call
MAX_TEXT_LENGTH = 50         # Max text length (chars)
MAX_SLOTS_PER_SAMPLE = 6     # Max slots per sample

# ══════════════════════════════════════════════════════════════════════
# Main generation function
# ══════════════════════════════════════════════════════════════════════

def generate_data():
    """Generate training data with LLM-based slot annotation."""
    import time
    from collections import Counter

    all_samples = []
    total_combinations = sum(len(subs) for subs in INTENT_SUBINTENT_MAP.values())
    current = 0

    for main_intent, sub_intents in INTENT_SUBINTENT_MAP.items():
        for sub_intent in sub_intents:
            current += 1
            target = INTENT_SAMPLE_TARGETS.get((main_intent, sub_intent), 150)
            print(f"\n[{current}/{total_combinations}] {main_intent}/{sub_intent} (target: {target})")

            batch_samples = []
            seen_texts = set()
            max_retries = (target // SAMPLES_PER_BATCH) + 10

            for batch_idx in range(max_retries):
                if len(batch_samples) >= target:
                    break

                start_time = time.time()
                print(f"  [batch {batch_idx + 1}]", end=" ")
                samples = generate_samples(main_intent, sub_intent, SAMPLES_PER_BATCH)
                elapsed = time.time() - start_time

                if not samples:
                    print(f"FAIL ({elapsed:.1f}s)")
                    continue

                new_count = 0
                for s in samples:
                    key = s["text"]
                    if key not in seen_texts:
                        seen_texts.add(key)
                        batch_samples.append(s)
                        new_count += 1

                print(f"+{new_count} ({elapsed:.1f}s), total: {len(batch_samples)}")
                time.sleep(0.3)

            # Validate
            valid = []
            for sample in batch_samples:
                ok = True
                for slot in sample["slots"]:
                    v = slot.get("value", "")
                    if slot["start"] >= slot["end"] or slot["end"] > len(sample["text"]):
                        ok = False
                        break
                    if sample["text"][slot["start"]:slot["end"]] != v:
                        real_start = sample["text"].find(v, max(0, slot["start"] - 5))
                        if real_start != -1 and real_start <= slot["start"] + 5:
                            slot["start"] = real_start
                            slot["end"] = real_start + len(v)
                        else:
                            ok = False
                            break
                if ok:
                    valid.append(sample)

            all_samples.extend(valid)
            print(f"  valid: {len(valid)}/{len(batch_samples)}")

    # Global dedup
    seen_global = set()
    deduped = []
    for s in all_samples:
        key = s["text"]
        if key not in seen_global:
            seen_global.add(key)
            deduped.append(s)

    dups_removed = len(all_samples) - len(deduped)
    all_samples = deduped

    output_dir = "data/joint_intent"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "train.jsonl")

    print(f"\n{'='*60}")
    print(f"Saving {len(all_samples)} samples to {output_file} (deduped {dups_removed})...")

    with open(output_file, "w", encoding="utf-8") as f:
        for sample in all_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")

    print(f"{'='*60}")
    print(f"Done! Total: {len(all_samples)} samples")

    intent_dist = Counter(s["main_intent"] for s in all_samples)
    sub_dist = Counter(s["sub_intent"] for s in all_samples)
    slot_count = sum(len(s["slots"]) for s in all_samples)
    print(f"\nMain intent distribution:")
    for intent, cnt in sorted(intent_dist.items()):
        print(f"  {intent}: {cnt}")
    print(f"\nSub intent distribution:")
    for sub, cnt in sorted(sub_dist.items()):
        print(f"  {sub}: {cnt}")
    print(f"\nTotal slots: {slot_count} (avg {slot_count / max(len(all_samples), 1):.1f}/sample)")


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    generate_data()
