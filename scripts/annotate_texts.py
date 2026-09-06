"""
从原始文本提取槽位并转换为JSON格式
输入：raw_texts.txt (格式: intent_type|sub_intent|text)
输出：train.jsonl
"""
import json
import os
import re


def auto_annotate_slots(text: str, intent_type: str, sub_intent: str) -> list:
    """
    自动标注槽位（基于规则）
    """
    slots = []
    
    # 定义槽位提取规则（正则表达式）
    patterns = {
        'budget_max': [
            r'预算(\d{3,5})',
            r'(\d{3,5})元以内',
            r'(\d{3,5})左右',
            r'(\d{3,5})块',
            r'(\d{3,5})以下',
            r'(\d{3,5})内',
        ],
        'brand': [
            r'(华为|小米|苹果|三星|荣耀|OPPO|vivo|联想|戴尔|索尼|海尔|格力|耐克|阿迪达斯|无印良品|戴森|优衣库|ZARA|安踏|李宁|周大福|星巴克)',
        ],
        'category': [
            r'(手机|笔记本|电脑|平板|耳机|电视|空调|冰箱|洗衣机|相机|手表|音箱|显示器|婴儿车|西装|运动鞋|连衣裙|帆布包|充电器|电饭煲|吸尘器|游戏本|蓝牙耳机|笔记本电脑|投影仪|扫地机器人|电动牙刷|智能手表|羽绒服|棉服|皮鞋|板鞋|跑鞋|童车|推车|背带|沙发|保温杯|电饭煲|压力锅|高压锅|洗地机|吹风机|手环)',
        ],
        'order_id': [
            r'(SO_\d+)',
            r'(订单号[是]?\s*(\d{6,20}))',
        ],
        'product_a': [
            r'(iPhone\s?\d+|RTX\s?\d{4}|MacBook\s?[A-Za-z]+|华为Mate\s?\d+|三星S\d+|PS5|Xbox\s?Series\s?[XXS]|Redmi\s?K\d+|一加\s?\d+|vivo\s?X\d+|OPPO\s?Find\s?X\d+|AirPods\s?Pro|索尼XM\d+|小米手环\s?\d+|华为GT\d+|ROG幻\d+|联想小新|雷蛇幻锋|松下EH-NA\d+)',
        ],
        'reason': [
            r'(质量不好|尺码不合适|不喜欢|不满意|买错了|不想要了)',
        ],
        'issue_type': [
            r'(不制冷|黑屏|不亮|屏幕碎|无法开机|坏了|漏水|不转|煮不熟|断连|刮花|缩水|失灵|噪音大|制冷差)',
        ],
        'location': [
            r'(北京|上海|广州|深圳|杭州|成都|重庆|南京|西安|附近)',
        ],
    }
    
    # 特殊处理：过滤尺寸误标为budget
    dimension_pattern = r'(\d{2,3})寸'
    dimension_matches = list(re.finditer(dimension_pattern, text))
    dimension_positions = set()
    for match in dimension_matches:
        for i in range(match.start(), match.end()):
            dimension_positions.add(i)
    
    # 应用规则
    for entity_type, pattern_list in patterns.items():
        for pattern in pattern_list:
            matches = re.finditer(pattern, text)
            for match in matches:
                value = match.group(1) if match.lastindex else match.group(0)
                
                # 过滤无效值
                if len(value) < 2 or value in ['和', '与', '对比', '哪个']:
                    continue
                
                # 过滤尺寸被误标为budget
                if entity_type == 'budget_max':
                    # 检查是否包含"寸"
                    if any(pos in dimension_positions for pos in range(match.start(), match.end())):
                        continue
                    # 检查是否是纯数字且后面紧跟"寸"
                    if re.match(r'^\d+$', value):
                        next_pos = match.end()
                        if next_pos < len(text) and text[next_pos] == '寸':
                            continue
                
                # 避免重叠
                overlap = False
                for existing_slot in slots:
                    if not (match.end() <= existing_slot['start'] or match.start() >= existing_slot['end']):
                        overlap = True
                        break
                
                if not overlap:
                    slots.append({
                        'entity': entity_type,
                        'start': match.start(),
                        'end': match.end(),
                        'value': value.strip()
                    })
    
    # 按start位置排序
    slots.sort(key=lambda x: x['start'])
    return slots


def convert_to_jsonl(input_file: str, output_file: str):
    """将原始文本转换为JSONL格式"""
    
    if not os.path.exists(input_file):
        print(f"❌ 文件不存在: {input_file}")
        return
    
    samples = []
    
    with open(input_file, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    for line_num, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        
        # 解析格式：intent_type|sub_intent|text
        parts = line.split('|', 2)
        if len(parts) != 3:
            print(f"⚠️  第{line_num}行格式错误: {line[:50]}")
            continue
        
        intent_type, sub_intent, text = parts
        
        # 自动标注槽位
        slots = auto_annotate_slots(text, intent_type, sub_intent)
        
        sample = {
            "text": text,
            "main_intent": intent_type,
            "sub_intent": sub_intent,
            "slots": slots
        }
        
        samples.append(sample)
    
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
    
    print(f"读取文件: {input_file}")
    convert_to_jsonl(input_file, output_file)
