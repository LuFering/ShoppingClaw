"""
使用LLM批量将原始文本转换为JSON格式（带槽位标注）
输入：raw_texts.txt (格式: intent_type|sub_intent|text)
输出：train.jsonl
优化：一次处理5条，减少API调用次数
"""
import json
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("DASHSCOPE_API_KEY")
API_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"


def annotate_batch_with_llm(batch_data: list) -> list:
    """使用LLM批量标注文本槽位（一次5条）"""
    
    # 构建批量prompt
    texts_info = []
    for i, (text, intent_type, sub_intent) in enumerate(batch_data):
        texts_info.append(f"""{i+1}. 文本：{text}
   意图：{intent_type}/{sub_intent}""")
    
    prompt = f"""
你是电商购物助手的槽位标注专家。请为以下{len(batch_data)}条用户query标注槽位。

## 待标注文本列表
{chr(10).join(texts_info)}

## 槽位类型定义
- budget_max：预算上限（如"5000"、"3000以内"），**注意：尺寸如"75寸"不是budget**
- brand：品牌名称（如"华为"、"小米"、"苹果"）
- category：商品品类（如"手机"、"笔记本"、"电视"）
- order_id：订单号（如"SO_12345"、"123456789"）
- product_a：对比的第一个商品（如"iPhone 15"、"RTX4060"）
- product_b：对比的第二个商品（如"小米14"、"RTX4070"）
- reason：退货原因（如"质量不好"、"尺码不合适"）
- issue_type：故障类型（如"不制冷"、"黑屏"、"屏幕碎"）
- location：地点（如"北京"、"上海"、"附近"）

## 标注规则
1. **尺寸不是预算**："75寸"、"55寸"等不要标为budget_max
2. **型号不是品牌**："Pro"、"Air"是产品型号一部分，不单独标brand
3. **unknown意图无槽位**：如果意图是unknown，slots必须为空数组[]
4. **位置准确**：start/end必须是Python切片位置，text[start:end] == value
5. **只标注明显实体**：不确定的不要标注

## 输出格式（严格JSON数组）
[
  {{
    "index": 1,
    "text": "文本内容",
    "main_intent": "意图类型",
    "sub_intent": "子意图",
    "slots": [
      {{"entity": "budget_max", "start": 6, "end": 10, "value": "5000"}}
    ]
  }}
]

**直接返回JSON数组，不要任何解释：**
"""
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": "qwen-turbo",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3
    }
    
    try:
        response = requests.post(API_URL, json=payload, headers=headers, timeout=15)
        response.raise_for_status()
        result = response.json()
        content = result["choices"][0]["message"]["content"].strip()
        
        # 移除Markdown代码块
        if content.startswith("```json"):
            content = content[7:]
        elif content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        content = content.strip()
        
        # 解析JSON数组
        samples = json.loads(content)
        return samples
        
    except Exception as e:
        print(f"  ❌ LLM批量标注失败: {e}")
        # 返回空槽位的默认结构
        return [
            {
                "index": i+1,
                "text": text,
                "main_intent": intent_type,
                "sub_intent": sub_intent,
                "slots": []
            }
            for i, (text, intent_type, sub_intent) in enumerate(batch_data)
        ]


def convert_to_jsonl(input_file: str, output_file: str):
    """将原始文本转换为JSONL格式（使用LLM批量标注）"""
    
    if not os.path.exists(input_file):
        print(f"❌ 文件不存在: {input_file}")
        return
    
    samples = []
    
    with open(input_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f.readlines() if line.strip()]
    
    total = len(lines)
    batch_size = 2
    print(f"开始处理 {total} 条文本（每批{batch_size}条）...\n")
    
    # 分批处理
    for batch_start in range(0, total, batch_size):
        batch_end = min(batch_start + batch_size, total)
        batch_lines = lines[batch_start:batch_end]
        
        # 解析批次数据
        batch_data = []
        for line in batch_lines:
            parts = line.split('|', 2)
            if len(parts) == 3:
                intent_type, sub_intent, text = parts
                batch_data.append((text, intent_type, sub_intent))
        
        if not batch_data:
            continue
        
        # 批量标注
        print(f"处理进度: {batch_start+1}-{batch_end}/{total}")
        batch_results = annotate_batch_with_llm(batch_data)
        
        # 按index排序并添加到samples
        batch_results.sort(key=lambda x: x.get("index", 0))
        samples.extend(batch_results)
        
        # 避免API限流
        time.sleep(1)
    
    # 保存为JSONL
    with open(output_file, "w", encoding="utf-8") as f:
        for sample in samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    
    print(f"\n{'='*60}")
    print(f"✅ 转换完成！")
    print(f"📊 总样本数: {len(samples)}")
    print(f"📁 保存路径: {output_file}")
    print(f"{'='*60}")
    
    # 统计意图分布
    from collections import Counter
    intent_dist = Counter([s["main_intent"] for s in samples])
    print("\n📈 意图分布:")
    for intent, count in sorted(intent_dist.items()):
        print(f"  {intent}: {count} 条")


if __name__ == "__main__":
    input_dir = "scripts/data/joint_intent"
    input_file = os.path.join(input_dir, "raw_texts.txt")
    output_file = os.path.join(input_dir, "train.jsonl")
    
    print(f"读取文件: {input_file}\n")
    convert_to_jsonl(input_file, output_file)
