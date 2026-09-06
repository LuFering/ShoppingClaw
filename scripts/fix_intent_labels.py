import json

# 读取数据
with open('scripts/data/joint_intent/train_merged.jsonl', 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()

corrected = []
for line in lines:
    try:
        data = json.loads(line)
    except json.JSONDecodeError:
        continue  # 跳过损坏的 JSON 行
    
    # 修正规则：无明确对比词（如"哪个"、"对比"、"和"）的推荐请求应为 single_product
    text = data['text']
    if data['main_intent'] == 'product_recommend' and data['sub_intent'] == 'multi_compare':
        # 检查是否包含对比关键词
        compare_keywords = ['哪个', '对比', '和', 'vs', 'VS', '比较', '差别', '区别']
        has_compare = any(kw in text for kw in compare_keywords)
        
        if not has_compare:
            data['sub_intent'] = 'single_product'
    
    corrected.append(json.dumps(data, ensure_ascii=False))

# 写回文件
with open('scripts/data/joint_intent/train_corrected.jsonl', 'w', encoding='utf-8') as f:
    f.write('\n'.join(corrected))

print(f"修正完成，共 {len(corrected)} 条数据")
