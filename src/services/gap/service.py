"""Gap Detector单例服务"""
import os
import joblib
import numpy as np
from typing import Dict, Any
from pathlib import Path
from src.services.gap.feature_extractor import FeatureExtractor
from src.services.gap.model import GapDetectorModel


class GapService:
    """Gap检测服务（懒加载单例）"""
    
    def __init__(self, model_dir: str = None):
        # 默认使用项目根目录下的 model/gap_detector，确保路径稳定性
        if model_dir is None:
            # 无论从哪里启动，都根据当前文件位置向上回溯到项目根目录
            current_file = Path(__file__).resolve()
            project_root = current_file.parents[3] # gap -> services -> src -> ShoppingClaw
            self.model_dir = str(project_root / "model" / "gap_detector")
        else:
            self.model_dir = model_dir
        self.feature_extractor = FeatureExtractor()
        self.model = None
        self._load_model()
    
    def _load_model(self):
        """加载训练好的模型"""
        multilabel_path = os.path.join(self.model_dir, "multilabel_model.joblib")
        confidence_path = os.path.join(self.model_dir, "confidence_model.joblib")
        
        if os.path.exists(multilabel_path) and os.path.exists(confidence_path):
            model = GapDetectorModel()
            model.multilabel_clf = joblib.load(multilabel_path)
            model.confidence_reg = joblib.load(confidence_path)
            self.model = model
            print(f"[GapService] 模型加载成功: {self.model_dir}")
        else:
            print(f"[GapService] 警告: 模型文件不存在，将使用规则模式")
            self.model = None
    
    def predict(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """预测证据缺口
        
        Args:
            state: 当前状态字典
            
        Returns:
            {
                "information_gaps": [...],
                "gap_probs": {...},
                "decision_confidence": 0.0-1.0,
                "model_confidence": 0.0-1.0
            }
        """
        # 提取特征
        features = self.feature_extractor.extract(state)
        features_2d = features.reshape(1, -1)
        
        if self.model is None:
            # 规则模式（降级方案）
            return self._rule_based_predict(state)
        
        # 模型推理
        gap_probs, confidence = self.model.predict(features_2d)
        
        # 后处理
        gaps = self._decode_gaps(gap_probs[0], threshold=0.6)
        gap_probs_dict = self._probs_to_dict(gap_probs[0])
        
        return {
            "information_gaps": gaps,
            "gap_probs": gap_probs_dict,
            "decision_confidence": float(np.clip(confidence[0], 0.0, 1.0)),
            "model_confidence": 0.81  # 简化版固定值
        }
    
    def _decode_gaps(self, probs: np.ndarray, threshold: float) -> list:
        """解码缺口标签"""
        gaps = []
        for i, prob in enumerate(probs):
            if prob >= threshold:
                gaps.append(GapDetectorModel.GAP_LABELS[i])
        
        # 如果没有缺口，标记为no_gap
        if not gaps:
            gaps = ["no_gap"]
        
        return gaps
    
    def _probs_to_dict(self, probs: np.ndarray) -> dict:
        """概率数组转字典"""
        return {
            label: float(prob)
            for label, prob in zip(GapDetectorModel.GAP_LABELS, probs)
        }
    
    def _rule_based_predict(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """规则模式（降级方案）"""
        intent = state.get("intent", {})
        evidence = state.get("evidence", {})
        
        gaps = []
        main_intent = intent.get("main_intent", "")
        
        # 规则1：商品推荐类需要research_data
        if main_intent in ["product_recommend", "price_check"]:
            if not evidence.get("research_data"):
                gaps.append("product_list")
        
        # 规则2：对比类需要analysis_report
        if intent.get("sub_intent") in ["multi_compare", "direct_compare"]:
            if not evidence.get("analysis_report"):
                gaps.append("comparison_matrix")
        
        # 规则3：售后类需要risk_audit
        if main_intent == "after_sales":
            if not evidence.get("risk_audit"):
                gaps.append("risk_audit")
        
        # 计算置信度
        intent_conf = intent.get("intent_confidence", 0.5)
        gap_penalty = len(gaps) * 0.15
        confidence = max(0.0, min(1.0, intent_conf * (1 - gap_penalty)))
        
        return {
            "information_gaps": gaps if gaps else ["no_gap"],
            "gap_probs": {gap: 0.8 for gap in gaps} if gaps else {"no_gap": 0.9},
            "decision_confidence": round(confidence, 4),
            "model_confidence": 0.5  # 规则模式置信度较低
        }


# 全局单例
_gap_service: GapService = None


def get_gap_service() -> GapService:
    """获取Gap检测服务单例"""
    global _gap_service
    if _gap_service is None:
        _gap_service = GapService()
    return _gap_service
