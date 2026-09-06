"""Gap Detector模型定义"""
import lightgbm as lgb
from sklearn.multioutput import MultiOutputClassifier
from typing import List, Tuple
import numpy as np


class GapDetectorModel:
    """LightGBM Gap检测模型"""
    
    # 缺口标签空间（8类）
    GAP_LABELS = [
        "human_input",
        "user_preference",
        "product_list",
        "price_or_stock",
        "comparison_matrix",
        "risk_audit",
        "evidence_quality",
        "no_gap"
    ]
    
    def __init__(self):
        # 多标签分类器（使用MultiOutputClassifier包装）
        base_clf = lgb.LGBMClassifier(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            objective='binary',
            random_state=42
        )
        self.multilabel_clf = MultiOutputClassifier(base_clf)
        
        # 回归器（决策置信度）
        self.confidence_reg = lgb.LGBMRegressor(
            n_estimators=100,
            max_depth=5,
            learning_rate=0.1,
            random_state=42
        )
    
    def train_multilabel(self, X: np.ndarray, y: np.ndarray):
        """训练多标签分类器
        
        Args:
            X: 特征矩阵 (n_samples, n_features)
            y: 标签矩阵 (n_samples, 8) 多标签二进制
        """
        self.multilabel_clf.fit(X, y)
    
    def train_confidence(self, X: np.ndarray, y: np.ndarray):
        """训练置信度回归器
        
        Args:
            X: 特征矩阵 (n_samples, n_features)
            y: 目标值 (n_samples,) 0-1连续值
        """
        self.confidence_reg.fit(X, y)
    
    def predict(self, X: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
        """预测缺口和置信度
        
        Args:
            X: 特征矩阵 (n_samples, n_features)
            
        Returns:
            gap_probs: 缺口概率 (n_samples, 8)
            confidence: 决策置信度 (n_samples,)
        """
        # 多标签分类器返回每个标签的概率
        gap_probs_list = []
        for estimator in self.multilabel_clf.estimators_:
            proba = estimator.predict_proba(X)
            # 取正类概率（第1列）
            gap_probs_list.append(proba[:, 1])
        
        gap_probs = np.column_stack(gap_probs_list)
        confidence = self.confidence_reg.predict(X)
        
        return gap_probs, confidence
