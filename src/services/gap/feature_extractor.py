"""特征提取器"""
import numpy as np
from typing import Dict, Any


class FeatureExtractor:
    """从state提取Gap检测特征"""
    
    # 主意图映射
    MAIN_INTENT_MAP = {
        "product_recommend": 0,
        "product_comparison": 1,
        "order_query": 2,
        "after_sales": 3,
        "price_check": 4,
        "store_search": 5,
        "unknown": 6
    }
    
    # 最后动作映射
    LAST_ACTION_MAP = {
        "researcher": 0,
        "analyst": 1,
        "critic": 2,
        "memory_manager": 3
    }
    
    def extract(self, state: Dict[str, Any]) -> np.ndarray:
        """提取16维特征向量"""
        intent = state.get("intent", {})
        
        # 兼容两种 State 结构：嵌套的 evidence 字典 vs 顶层字段
        evidence = state.get("evidence", {})
        if not evidence or not isinstance(evidence, dict):
            # 如果 evidence 不存在或不是字典，则从顶层读取 (适配 MasterContext)
            evidence = {
                "research_data": state.get("research_data"),
                "analysis_report": state.get("analysis_report"),
                "risk_audit": state.get("risk_audit"),
                "user_profile": state.get("user_profile")
            }
        
        features = []
        
        # 1. 意图特征（9维：置信度+缺失槽位数+7维独热编码）
        features.append(intent.get("intent_confidence", 0.0))
        features.append(len(intent.get("missing_slots", [])))
        
        # 主意图独热编码
        main_intent = intent.get("main_intent", "unknown")
        intent_onehot = [0] * 7
        intent_idx = self.MAIN_INTENT_MAP.get(main_intent, 6)
        intent_onehot[intent_idx] = 1
        features.extend(intent_onehot)
        
        # 2. 证据存在性（4维）
        features.append(1.0 if evidence.get("research_data") else 0.0)
        features.append(1.0 if evidence.get("analysis_report") else 0.0)
        features.append(1.0 if evidence.get("risk_audit") else 0.0)
        features.append(1.0 if evidence.get("user_profile") else 0.0)
        
        # 3. 证据质量（5维）
        research_data = evidence.get("research_data") or []
        products = research_data.get("products", []) if isinstance(research_data, dict) else []
        features.append(len(products))  # 商品数量
        
        # 品牌多样性
        brands = set()
        for p in products:
            if isinstance(p, dict) and "brand" in p:
                brands.add(p["brand"])
        features.append(len(brands))
        
        # 价格覆盖率（简化版：有价格数据的商品比例）
        if products:
            priced = sum(1 for p in products if isinstance(p, dict) and p.get("price"))
            features.append(priced / len(products))
        else:
            features.append(0.0)
        
        # 分析维度数
        analysis_report = evidence.get("analysis_report") or {}
        dimensions = analysis_report.get("key_decision_dimensions", [])
        features.append(len(dimensions))
        
        # 风险红灯数
        risk_audit = evidence.get("risk_audit") or {}
        risks = risk_audit.get("risks", [])
        red_count = sum(1 for r in risks if r.get("level") == "red")
        features.append(red_count)
        
        # 4. 上下文特征（3维）
        # 优先从 state 顶层读取 evidence_log，兼容 MasterContext
        evidence_log = state.get("evidence_log", [])
        if not evidence_log:
            evidence_log = state.get("evidence", {}).get("evidence_log", [])
        features.append(len(evidence_log))  # 轮次
        
        # 最后动作
        if evidence_log:
            last_action = evidence_log[-1].get("type", "")
            action_code = self.LAST_ACTION_MAP.get(last_action, 0)
        else:
            action_code = 0
        features.append(float(action_code))
        
        # 证据日志长度
        features.append(len(evidence_log))
        
        return np.array(features)
