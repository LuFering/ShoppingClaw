"""
LLM生成原始文本数据
输出：每行一条用户query文本
"""
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("DASHSCOPE_API_KEY")
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"

# 意图体系定义
INTENT_SUBINTENT_MAP = {
    "product_recommend": ["single_product", "multi_compare"],
    "product_comparison": ["direct_compare", "category_compare"],
    "order_query": ["status_check", "logistics_track"],
    "after_sales": ["return_request", "repair_request"],
    "price_check": ["none"],
    "store_search": ["none"],
    "unknown": ["none"]
}

# 业务场景参考（完整版）
SCENARIO_GUIDE = {
    "product_recommend": {
        "single_product": """
用户需要推荐单个商品，典型场景：
- 数码3C："想买个游戏本，预算8000左右，主要玩3A大作，偶尔剪视频"
- 家电家居："新家装修，客厅要买台电视，75寸，画质好点的"
- 服饰美妆："面试要穿正式点，想买套西装，预算1000左右"
- 母婴育儿："宝宝快出生了，要买婴儿车，轻便好收纳的"

槽位要求：
- category（必填）：商品品类
- budget_max（常见）：预算上限
- brand（可选）：品牌偏好
- usage_scenario（可选）：使用场景

表达风格多样化：
- 口语化："帮我找个..."、"想入手一个..."
- 省略句："预算5000的手机"、"降噪好的耳机"
- 疑问句："有没有适合跑步的运动鞋？"
""",
        "multi_compare": """
用户需要在多个维度对比后推荐，典型场景：
- "预算5000，推荐最值得买的手机"（性能/拍照/品牌权衡）
- "想买无线耳机，降噪要好，主要通勤用，预算500内"

槽位要求：
- category（必填）：商品品类
- budget_min/budget_max：预算范围
- brands：多个品牌候选
"""
    },
    "product_comparison": {
        "direct_compare": """
用户明确指定两个商品进行对比，典型场景：
- "iPhone 15和小米14哪个好"
- "RTX4060和4070显卡差多少"
- "OLED、Mini-LED、QLED电视哪种好"

槽位要求：
- product_a（必填）：第一个商品
- product_b（必填）：第二个商品
- dimensions（可选）：对比维度
""",
        "category_compare": """
用户在品类内对比不同型号/品牌，典型场景：
- "变频空调和定频空调哪个省电"
- "铝框行李箱和拉链箱哪个耐用"

槽位要求：
- category（必填）：商品品类
- budget_range（可选）：预算范围
"""
    },
    "order_query": {
        "status_check": """
用户查询订单状态，典型场景：
- "订单SO_12345到哪了"
- "我昨天买的衣服发货了吗"
- "查一下订单123456789的状态"

槽位要求：
- order_id（必填）：订单号
""",
        "logistics_track": """
用户追踪物流信息，典型场景：
- "我的快递到哪了"
- "物流怎么三天没更新了"

槽位要求：
- order_id（必填）：订单号或快递单号
"""
    },
    "after_sales": {
        "return_request": """
用户咨询退货相关问题，典型场景：
- "这个能退货吗"
- "不满意退货麻烦吗"
- "买了三天能退吗"

槽位要求：
- order_id（常见）：关联订单号
- reason（可选）：退货原因
""",
        "repair_request": """
用户咨询维修/售后问题，典型场景：
- "手机屏幕摔坏了能修吗"
- "空调不制冷了怎么办"

槽位要求：
- order_id（可选）：关联订单号
- issue_type（必填）：问题类型
"""
    },
    "price_check": """
用户咨询价格趋势/促销时机，**不是询问商品价格或预算**。

典型场景（必须包含时间/价格趋势关键词）：
- "这个商品现在买值不值"
- "什么时候买最便宜"
- "双11会降价吗"
- "这个价格是不是被商家先涨后降"
- "最近有优惠吗"
- "等618再买会不会更便宜"

**错误示例（这些是product_recommend，不是price_check）**：
- ❌ "帮我找3000以内的笔记本" → 这是推荐商品
- ❌ "想买个500的耳机" → 这是推荐商品

槽位要求：
- category（必填）：商品品类
- brand（可选）：品牌
- **严禁标注budget_max/budget_min**
""",
    "store_search": """
用户搜索线下实体店/门店位置，**不是在线购买商品**。

典型场景（必须包含地点/实体店关键词）：
- "附近有哪些华为专卖店"
- "北京哪里有苹果直营店"
- "这个品牌有实体店吗"
- "上海耐克门店在哪里"
- "小米之家在哪"

**错误示例（这些是product_recommend，不是store_search）**：
- ❌ "想买个3000以内的小米电脑" → 这是在线购物
- ❌ "帮我找苹果的耳机" → 这是推荐商品

槽位要求：
- brand（必填）：品牌名称
- location（可选）：地点
- **严禁标注budget_max/category**
""",
    "unknown": """
无法识别意图或纯闲聊，**没有任何购物相关需求**。

典型场景：
- "今天天气怎么样"
- "你好"
- "你是谁"
- "谢谢"
- "在吗"

**错误示例（这些有明确意图，不是unknown）**：
- ❌ "帮我找2000的笔记本" → 这是product_recommend
- ❌ "有没有好看的连衣裙" → 这是product_recommend
- ❌ "想买个便宜的耳机" → 这是product_recommend

槽位要求：
- slots必须为空数组 []
- **严禁标注任何槽位**
"""
}

SAMPLES_PER_BATCH = 10  # 每批生成10条（提升多样性）
BATCHES_PER_COMBINATION = 4  # 每个组合生成4批，总计40条


def generate_texts(intent_type: str, sub_intent: str, count: int) -> list:
    """调用LLM生成纯文本列表"""
    
    # 获取业务场景
    intent_config = SCENARIO_GUIDE.get(intent_type, {})
    if isinstance(intent_config, dict):
        guide = intent_config.get(sub_intent, str(intent_config))
    else:
        guide = str(intent_config)
    
    random_seed = int(time.time() * 1000) % 10000
    
    prompt = f"""
你是电商购物助手的数据生成专家。请生成{count}条**完全不同**的用户query文本。

## 当前任务
- 主意图：{intent_type}
- 子意图：{sub_intent}
- **随机种子**：{random_seed}

## 业务场景参考
{guide}

## 输出要求（**必须严格遵守**）
1. **严禁重复**：生成的{count}条文本必须完全不同，句式、品类、品牌、表达方式都要变化
2. **真实性**：口语化表达，避免机械重复和模板化
3. **长度控制**：每条文本在6-30字之间
4. **纯文本输出**：每行一条文本，不要编号、不要JSON、不要任何解释
5. **句式多样化**：混合使用以下句式，不要全部相同
   - 陈述句："想买个降噪耳机"
   - 疑问句："有没有适合跑步的鞋？"
   - 省略句："预算5000的手机"
   - 倒装句："降噪好的耳机有吗"
   - 场景化："面试要穿西装，推荐一套"
   - 对比式："A和B哪个更好"
6. **品类多样化**：每次生成要覆盖不同品类（数码、家电、服饰、母婴等），不要集中在单一品类
7. **品牌多样化**：如果涉及品牌，要使用不同品牌，不要重复同一品牌

**直接返回纯文本列表，每行一条：**
"""
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "qwen3.5-plus",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.7
    }
    
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=10)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()
        
        # 移除Markdown代码块
        if content.startswith("```"):
            content = content.split('\n', 1)[1]
        if content.endswith("```"):
            content = content.rsplit('\n', 1)[0]
        
        # 解析为文本列表（放宽长度限制）
        lines = []
        for line in content.split('\n'):
            text = line.strip()
            if not text:
                continue
            # 长度控制：6-30字
            if 6 <= len(text) <= 30:
                lines.append(text)
            elif len(text) < 6:
                print(f"  ⚠️  跳过过短文本: {text}")
            else:
                print(f"  ⚠️  跳过过长文本: {text[:40]}...")
        return lines
        
    except Exception as e:
        print(f"  ❌ API调用失败: {e}")
        return []


if __name__ == "__main__":
    output_dir = "data/joint_intent"
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "raw_texts.txt")
    
    all_texts = []
    total_combinations = sum(len(subs) for subs in INTENT_SUBINTENT_MAP.values())
    current = 0
    
    for main_intent, sub_intents in INTENT_SUBINTENT_MAP.items():
        for sub_intent in sub_intents:
            current += 1
            print(f"\n[{current}/{total_combinations}] 生成 {main_intent} / {sub_intent}...")
            
            batch_texts = []
            seen_texts = set()
            
            for batch_idx in range(BATCHES_PER_COMBINATION):
                start_time = time.time()
                print(f"  🔄 第 {batch_idx + 1}/{BATCHES_PER_COMBINATION} 批...")
                
                texts = generate_texts(main_intent, sub_intent, SAMPLES_PER_BATCH)
                elapsed = time.time() - start_time
                
                # 去重
                new_count = 0
                for text in texts:
                    if text not in seen_texts:
                        seen_texts.add(text)
                        # 保存格式：intent_type|sub_intent|text
                        batch_texts.append(f"{main_intent}|{sub_intent}|{text}")
                        new_count += 1
                
                if new_count == 0:
                    print(f"  ⚠️  本批数据全部重复 (耗时: {elapsed:.1f}s)")
                else:
                    print(f"  ✅ 新增 {new_count} 条有效文本 (耗时: {elapsed:.1f}s)")
                
                if len(batch_texts) >= BATCHES_PER_COMBINATION * SAMPLES_PER_BATCH:
                    break
            
            all_texts.extend(batch_texts)
            print(f"  ✅ 本组合有效文本: {len(batch_texts)}")
    
    # 保存原始文本
    print(f"\n准备保存 {len(all_texts)} 条文本到 {output_file}...")
    try:
        with open(output_file, "w", encoding="utf-8") as f:
            for line in all_texts:
                f.write(line + "\n")
        print(f"✅ 文件写入成功")
    except Exception as e:
        print(f"❌ 保存失败: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
    
    print(f"\n{'='*60}")
    print(f"✅ 文本生成完成！")
    print(f"📊 总文本数: {len(all_texts)}")
    print(f"📁 保存路径: {output_file}")
    print(f"{'='*60}")
