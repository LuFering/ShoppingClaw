"""训练数据生成器 - 规则合成"""
import json
import random
from pathlib import Path


def generate_training_data(n_samples: int = 500):
    """生成训练数据样本
    
    基于规则合成不同场景的状态快照和标签
    """
    
    samples = []
    
    # 场景模板
    scenarios = [
        # 场景1：商品推荐，无商品列表
        {
            "intent": {"main_intent": "product_recommend", "sub_intent": "single_product", "intent_confidence": 0.85, "missing_slots": []},
            "evidence": {"research_data": None, "analysis_report": None, "risk_audit": None, "user_profile": None},
            "evidence_log": [],
            "labels": {
                "information_gaps": ["product_list"],
                "decision_confidence": 0.72  # 0.85 * (1 - 0.15)
            }
        },
        
        # 场景2：商品推荐，有商品列表
        {
            "intent": {"main_intent": "product_recommend", "sub_intent": "single_product", "intent_confidence": 0.85, "missing_slots": []},
            "evidence": {
                "research_data": {"products": [{"brand": "华为"}, {"brand": "小米"}, {"brand": "苹果"}]},
                "analysis_report": None,
                "risk_audit": None,
                "user_profile": {"price_sensitivity": "medium"}
            },
            "evidence_log": [{"type": "product_list"}],
            "labels": {
                "information_gaps": ["no_gap"],
                "decision_confidence": 0.85
            }
        },
        
        # 场景3：对比意图，无分析
        {
            "intent": {"main_intent": "product_comparison", "sub_intent": "direct_compare", "intent_confidence": 0.9, "missing_slots": []},
            "evidence": {
                "research_data": {"products": [{"brand": "华为"}, {"brand": "小米"}]},
                "analysis_report": None,
                "risk_audit": None,
                "user_profile": None
            },
            "evidence_log": [{"type": "product_list"}],
            "labels": {
                "information_gaps": ["comparison_matrix"],
                "decision_confidence": 0.76  # 0.9 * (1 - 0.15)
            }
        },
        
        # 场景4：售后意图，无风险评估
        {
            "intent": {"main_intent": "after_sales", "sub_intent": "return_request", "intent_confidence": 0.8, "missing_slots": ["order_id"]},
            "evidence": {
                "research_data": None,
                "analysis_report": None,
                "risk_audit": None,
                "user_profile": None
            },
            "evidence_log": [],
            "labels": {
                "information_gaps": ["human_input", "risk_audit"],
                "decision_confidence": 0.54  # 0.8 * (1 - 0.3)
            }
        },
        
        # 场景5：完整证据链
        {
            "intent": {"main_intent": "product_recommend", "sub_intent": "multi_compare", "intent_confidence": 0.9, "missing_slots": []},
            "evidence": {
                "research_data": {"products": [{"brand": "华为", "price": 5000}, {"brand": "小米", "price": 4000}, {"brand": "苹果", "price": 6000}]},
                "analysis_report": {"key_decision_dimensions": ["性能", "价格", "续航"]},
                "risk_audit": {"risks": [{"level": "yellow"}]},
                "user_profile": {"price_sensitivity": "low"}
            },
            "evidence_log": [{"type": "product_list"}, {"type": "comparison_matrix"}, {"type": "risk_report"}],
            "labels": {
                "information_gaps": ["no_gap"],
                "decision_confidence": 0.9
            }
        },
        
        # 场景6：低置信度意图
        {
            "intent": {"main_intent": "unknown", "sub_intent": None, "intent_confidence": 0.3, "missing_slots": []},
            "evidence": {
                "research_data": None,
                "analysis_report": None,
                "risk_audit": None,
                "user_profile": None
            },
            "evidence_log": [],
            "labels": {
                "information_gaps": ["human_input"],
                "decision_confidence": 0.3
            }
        },
        
        # 场景7：问候语，无需补证
        {
            "intent": {"main_intent": "greeting", "sub_intent": None, "intent_confidence": 0.8, "missing_slots": []},
            "evidence": {
                "research_data": None,
                "analysis_report": None,
                "risk_audit": None,
                "user_profile": None
            },
            "evidence_log": [],
            "labels": {
                "information_gaps": ["no_gap"],
                "decision_confidence": 0.8
            }
        }
    ]
    
    # 生成样本
    for i in range(n_samples):
        scenario = random.choice(scenarios)
        
        # 添加随机扰动
        intent_confidence = scenario["intent"]["intent_confidence"] + random.uniform(-0.05, 0.05)
        intent_confidence = max(0.1, min(1.0, intent_confidence))
        
        sample = {
            "intent": {
                **scenario["intent"],
                "intent_confidence": round(intent_confidence, 4)
            },
            "evidence": scenario["evidence"],
            "evidence_log": scenario["evidence_log"],
            "labels": {
                "information_gaps": scenario["labels"]["information_gaps"],
                "decision_confidence": round(scenario["labels"]["decision_confidence"] + random.uniform(-0.05, 0.05), 4)
            }
        }
        
        samples.append(sample)
    
    return samples


if __name__ == "__main__":
    print("生成训练数据...")
    
    # 创建目录
    Path("data/gap_detector").mkdir(parents=True, exist_ok=True)
    
    # 生成数据
    data = generate_training_data(n_samples=500)
    
    # 拆分训练集/验证集
    random.shuffle(data)
    split_idx = int(len(data) * 0.8)
    train_data = data[:split_idx]
    val_data = data[split_idx:]
    
    # 保存
    with open("data/gap_detector/train.jsonl", "w", encoding="utf-8") as f:
        for sample in train_data:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    
    with open("data/gap_detector/val.jsonl", "w", encoding="utf-8") as f:
        for sample in val_data:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    
    print(f"✅ 训练数据生成完成")
    print(f"   训练集: {len(train_data)} 条")
    print(f"   验证集: {len(val_data)} 条")
    print(f"   保存位置: data/gap_detector/")
