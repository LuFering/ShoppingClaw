"""训练LightGBM Gap检测模型"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import joblib
import numpy as np
from src.services.gap.feature_extractor import FeatureExtractor
from src.services.gap.model import GapDetectorModel


def load_data(file_path: str):
    """加载JSONL数据"""
    samples = []
    with open(file_path, "r", encoding="utf-8") as f:
        for line in f:
            samples.append(json.loads(line))
    return samples


def prepare_features(samples, feature_extractor):
    """准备特征矩阵和标签"""
    X = []
    y_gaps = []
    y_confidence = []
    
    GAP_LABELS = GapDetectorModel.GAP_LABELS
    
    for sample in samples:
        # 构建state字典
        state = {
            "intent": sample["intent"],
            "evidence": sample["evidence"],
            "evidence_log": sample["evidence_log"]
        }
        
        # 提取特征
        features = feature_extractor.extract(state)
        X.append(features)
        
        # 准备缺口标签（多标签二进制编码）
        gap_labels = sample["labels"]["information_gaps"]
        gap_binary = [1.0 if label in gap_labels else 0.0 for label in GAP_LABELS]
        y_gaps.append(gap_binary)
        
        # 准备置信度标签
        y_confidence.append(sample["labels"]["decision_confidence"])
    
    return np.array(X), np.array(y_gaps), np.array(y_confidence)


def train():
    """训练模型"""
    print("=" * 60)
    print("训练Gap Detector模型")
    print("=" * 60)
    
    # 1. 加载数据
    print("\n[1/4] 加载训练数据...")
    train_samples = load_data("data/gap_detector/train.jsonl")
    val_samples = load_data("data/gap_detector/val.jsonl")
    print(f"   训练集: {len(train_samples)} 条")
    print(f"   验证集: {len(val_samples)} 条")
    
    # 2. 准备特征
    print("\n[2/4] 提取特征...")
    feature_extractor = FeatureExtractor()
    X_train, y_train_gaps, y_train_conf = prepare_features(train_samples, feature_extractor)
    X_val, y_val_gaps, y_val_conf = prepare_features(val_samples, feature_extractor)
    print(f"   特征维度: {X_train.shape[1]}")
    print(f"   训练集形状: X={X_train.shape}, y_gaps={y_train_gaps.shape}, y_conf={y_train_conf.shape}")
    
    # 3. 训练模型
    print("\n[3/4] 训练LightGBM模型...")
    model = GapDetectorModel()
    
    # 训练多标签分类器
    print("   训练多标签分类器...")
    model.train_multilabel(X_train, y_train_gaps)
    train_gap_preds = model.multilabel_clf.predict(X_train)
    train_gap_acc = (train_gap_preds == y_train_gaps).mean()
    val_gap_preds = model.multilabel_clf.predict(X_val)
    val_gap_acc = (val_gap_preds == y_val_gaps).mean()
    print(f"   训练集准确率: {train_gap_acc:.4f}")
    print(f"   验证集准确率: {val_gap_acc:.4f}")
    
    # 训练置信度回归器
    print("   训练置信度回归器...")
    model.train_confidence(X_train, y_train_conf)
    train_conf_mae = np.abs(model.confidence_reg.predict(X_train) - y_train_conf).mean()
    val_conf_mae = np.abs(model.confidence_reg.predict(X_val) - y_val_conf).mean()
    print(f"   训练集MAE: {train_conf_mae:.4f}")
    print(f"   验证集MAE: {val_conf_mae:.4f}")
    
    # 4. 保存模型
    print("\n[4/4] 保存模型...")
    model_dir = Path("model/gap_detector")
    model_dir.mkdir(parents=True, exist_ok=True)
    
    joblib.dump(model.multilabel_clf, model_dir / "multilabel_model.joblib")
    joblib.dump(model.confidence_reg, model_dir / "confidence_model.joblib")
    
    print(f"   模型已保存: {model_dir}")
    print("=" * 60)
    print("✅ 训练完成！")
    print("=" * 60)


if __name__ == "__main__":
    train()
