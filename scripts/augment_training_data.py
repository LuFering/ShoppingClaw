import json
import random

# 读取现有数据
lines = []
with open('scripts/data/joint_intent/train_final.jsonl', 'r', encoding='utf-8', errors='ignore') as f:
    for line in f:
        try:
            lines.append(json.loads(line.strip()))
        except json.JSONDecodeError:
            continue

# 同义词映射
synonyms = {
    "推荐": ["介绍", "安利", "建议"],
    "想买": ["想入手", "打算买", "准备购"],
    "有没有": ["有没", "是否存在"],
    "哪个": ["哪一个", "哪款"],
    "好用": ["实用", "靠谱", "不错"],
    "性价比高": ["划算", "值得", "实惠"],
}

def augment_text(text):
    """简单的同义词替换增强"""
    words = list(text)
    for orig, reps in synonyms.items():
        if orig in text and random.random() < 0.3:
            replacement = random.choice(reps)
            text = text.replace(orig, replacement, 1)
    return text

# 生成增强数据
augmented = []
for item in lines:
    # 对每条数据生成 2 个变体
    for _ in range(2):
        new_text = augment_text(item['text'])
        if new_text != item['text']:
            augmented.append({
                **item,
                'text': new_text
            })

# 合并并保存
all_data = lines + augmented
random.shuffle(all_data)

with open('scripts/data/joint_intent/train_augmented.jsonl', 'w', encoding='utf-8') as f:
    for item in all_data:
        f.write(json.dumps(item, ensure_ascii=False) + '\n')

print(f"原始数据: {len(lines)} 条")
print(f"增强后: {len(all_data)} 条")
