## 📍 BERT模型注入位置

### 1. **模型加载点**：`src/services/intent_service.py` 第53-70行

```python
def _load_models(self):
    """懒加载BERT模型"""
    if self._business_model is None:
        print(f"[IntentService] 加载业务意图分类器: {self._bert_model_path}")
        self._tokenizer = AutoTokenizer.from_pretrained(self._bert_model_path)
        
        # 业务意图分类器
        self._business_model = AutoModelForSequenceClassification.from_pretrained(
            self._bert_model_path,
            num_labels=len(self.business_intents)  # ← 7个标签
        ).to(self.device)
```


**关键参数**：
- `self._bert_model_path`：模型路径，默认 `"hfl/chinese-roberta-wwm-ext"`
- `num_labels=7`：对应7个业务意图类别

---

### 2. **配置入口**：`src/agents/common/middleware/intent_detector.py` 第18-34行

```python
def __init__(
        self,
        bert_model_path: str = "hfl/chinese-roberta-wwm-ext",  # ← 改这里
        confidence_threshold: float = 0.6,
        device: str = None
):
    self.intent_service = IntentService(
        bert_model_path=bert_model_path,  # ← 传递给Service
        confidence_threshold=confidence_threshold,
        device=device
    )
```


---

### 3. **Graph集成点**：`src/agents/master_agent/graph.py` 第107-112行（需补充）

```python
# 当前代码缺失，应添加：
intent_middleware = IntentDetectorMiddleware(
    bert_model_path="hfl/chinese-roberta-wwm-ext",  # ← 改这里换模型
    confidence_threshold=0.6
)
```


---

## 🔧 更换模型需修改的位置

### **最小改动方案**（仅换预训练模型）

只需改1处：

```python
# src/agents/master_agent/graph.py
intent_middleware = IntentDetectorMiddleware(
    bert_model_path="bert-base-chinese",  # ← 改成新模型名
    confidence_threshold=0.6
)
```


**支持的模型来源**：
- HuggingFace官方：`"bert-base-chinese"`, `"hfl/chinese-roberta-wwm-ext"`
- 本地路径：`"./models/my_finetuned_intent_model"`

---

### **完整替换方案**（换架构+微调）

需改3处：

#### ① 修改意图标签数量（如果新模型输出维度不同）

```python
# src/services/intent_service.py 第37-40行
self.business_intents = [
    "product_recommend", "product_comparison", "order_query", 
    "after_sales", "price_check", "store_search", "unknown"
]  # ← 如果新任务只有5类，改成5个
```


#### ② 修改模型加载逻辑（如果不用Transformer）

```python
# src/services/intent_service.py 第60-63行
self._business_model = AutoModelForSequenceClassification.from_pretrained(
    self._bert_model_path,
    num_labels=len(self.business_intents)  # ← 自动适配标签数
).to(self.device)
```


#### ③ 更新版本号（用于观测）

```python
# src/services/intent_service.py 第262行
model_version="bert_v2.0",  # ← 手动升级版本号
```


---

## 🏋️ 训练模块位置

### **当前状态**：❌ **不存在训练模块**

项目中**没有**完整的训练流程代码。现有实现是：
- 直接使用预训练模型 `hfl/chinese-roberta-wwm-ext`
- 未经过意图分类任务的微调（Fine-tuning）
- 实际效果≈随机猜测（因为预训练任务是MLM，不是分类）

---

## 🚀 完整训练→生产流程

### **Step 1: 准备标注数据**

创建文件：`data/intent_training/train.jsonl`

```jsonl
{"text": "推荐一款3000元的手机", "label": "product_recommend"}
{"text": "iPhone 15和小米14哪个好", "label": "product_comparison"}
{"text": "我的订单SO_12345到哪了", "label": "order_query"}
{"text": "这个能退货吗", "label": "after_sales"}
{"text": "今天有什么优惠", "label": "price_check"}
{"text": "附近有哪些店铺", "label": "store_search"}
{"text": "你好", "label": "unknown"}
```


**建议数据量**：每类至少500条，总计3500+条

---

### **Step 2: 创建训练脚本**

创建文件：`scripts/train_intent_bert.py`

```python
import json
from datasets import Dataset
from transformers import (
    AutoTokenizer, 
    AutoModelForSequenceClassification,
    TrainingArguments, 
    Trainer,
    DataCollatorWithPadding
)
from sklearn.metrics import accuracy_score, f1_score
import numpy as np

# ==================== 1. 加载数据 ====================
def load_dataset_from_jsonl(file_path: str):
    texts = []
    labels = []
    label_map = {
        "product_recommend": 0,
        "product_comparison": 1,
        "order_query": 2,
        "after_sales": 3,
        "price_check": 4,
        "store_search": 5,
        "unknown": 6
    }
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            texts.append(item["text"])
            labels.append(label_map[item["label"]])
    
    return Dataset.from_dict({"text": texts, "label": labels})

train_dataset = load_dataset_from_jsonl("data/intent_training/train.jsonl")

# ==================== 2. 加载预训练模型 ====================
model_name = "hfl/chinese-roberta-wwm-ext"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForSequenceClassification.from_pretrained(
    model_name, 
    num_labels=7
)

# ==================== 3. Tokenize ====================
def tokenize_function(examples):
    return tokenizer(
        examples["text"], 
        padding="max_length", 
        truncation=True, 
        max_length=128
    )

tokenized_datasets = train_dataset.map(tokenize_function, batched=True)

# ==================== 4. 定义评估指标 ====================
def compute_metrics(eval_pred):
    logits, labels = eval_pred
    predictions = np.argmax(logits, axis=-1)
    accuracy = accuracy_score(labels, predictions)
    f1 = f1_score(labels, predictions, average="weighted")
    return {"accuracy": accuracy, "f1": f1}

# ==================== 5. 训练配置 ====================
training_args = TrainingArguments(
    output_dir="./model/intent_bert_finetuned",
    num_train_epochs=3,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=32,
    learning_rate=2e-5,
    weight_decay=0.01,
    save_strategy="epoch",
    evaluation_strategy="epoch",
    load_best_model_at_end=True,
    metric_for_best_model="f1",
    logging_steps=50,
    report_to="none"  # 禁用wandb
)

# ==================== 6. 启动训练 ====================
data_collator = DataCollatorWithPadding(tokenizer=tokenizer)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=tokenized_datasets,
    eval_dataset=tokenized_datasets,  # 实际应拆分验证集
    tokenizer=tokenizer,
    data_collator=data_collator,
    compute_metrics=compute_metrics
)

trainer.train()

# ==================== 7. 保存模型 ====================
trainer.save_model("./model/intent_bert_finetuned")
tokenizer.save_pretrained("./model/intent_bert_finetuned")

print("✅ 训练完成！模型保存在 ./model/intent_bert_finetuned")
```


---

### **Step 3: 执行训练**

```bash
cd D:\ShoppingClaw
uv run python scripts/train_intent_bert.py
```


**训练耗时**：
- CPU：约2-4小时
- GPU（RTX 3090）：约15-30分钟

---

### **Step 4: 验证模型效果**

创建测试脚本：`scripts/test_intent_model.py`

```python
from src.services.intent_service import IntentService

# 加载微调后的模型
service = IntentService(
    bert_model_path="./model/intent_bert_finetuned",
    confidence_threshold=0.6
)

# 测试用例
test_cases = [
    "推荐一款3000元的手机",
    "iPhone 15和小米14对比",
    "订单SO_12345查询",
    "这个能退货吗"
]

for text in test_cases:
    result = service.recognize_intent(text)
    print(f"输入: {text}")
    print(f"意图: {result.business_intent} (置信度: {result.intent_confidence:.2f})")
    print(f"槽位: {result.slots}")
    print("-" * 50)
```


---

### **Step 5: 部署到生产**

#### 方案A：本地加载（开发环境）

```python
# src/agents/master_agent/graph.py
intent_middleware = IntentDetectorMiddleware(
    bert_model_path="./model/intent_bert_finetuned",  # ← 指向微调模型
    confidence_threshold=0.6
)
```


#### 方案B：模型服务器（生产环境）

**1. 启动FastAPI服务**：`services/intent_api.py`

```python
from fastapi import FastAPI
from pydantic import BaseModel
from src.services.intent_service import IntentService

app = FastAPI()
service = IntentService(bert_model_path="./model/intent_bert_finetuned")

class IntentRequest(BaseModel):
    text: str

@app.post("/predict")
def predict(request: IntentRequest):
    result = service.recognize_intent(request.text)
    return result.dict()

# 启动：uvicorn services.intent_api:app --host 0.0.0.0 --port 8000
```


**2. Middleware改为HTTP调用**：

```python
# src/agents/common/middleware/intent_detector.py
import requests

def before_agent(self, state: dict, runtime: Runtime) -> Command:
    user_input = state["messages"][-1].content
    
    # 调用远程服务
    response = requests.post(
        "http://intent-service:8000/predict",
        json={"text": user_input}
    )
    intent_dict = response.json()
    
    return Command(update={"intent": intent_dict})
```


---

## 📊 训练→生产完整流程图

```
标注数据 (train.jsonl)
  ↓
训练脚本 (scripts/train_intent_bert.py)
  ├─ 加载预训练模型 (hfl/chinese-roberta-wwm-ext)
  ├─ Tokenize + Fine-tuning (3 epochs)
  └─ 保存微调模型 (./models/intent_bert_finetuned/)
  ↓
验证脚本 (scripts/test_intent_model.py)
  ├─ 准确率 > 85%？ → 是 → 进入部署
  └─ 否 → 增加数据/调整超参 → 重新训练
  ↓
部署方案选择
  ├─ 开发环境：本地加载 (graph.py直接引用路径)
  └─ 生产环境：微服务化 (FastAPI + Docker)
  ↓
监控与迭代
  ├─ 收集线上bad case
  ├─ 标注新数据
  └─ 定期重新训练 (v1.0 → v1.1 → v2.0)
```


---

## ⚠️ 关键注意事项

1. **当前模型未训练**：直接用预训练模型效果很差，必须先微调
2. **数据质量决定上限**：标注错误会导致模型学偏
3. **GPU加速必备**：CPU训练太慢，建议租用云服务器（阿里云PAI/AWS SageMaker）
4. **版本管理**：每次训练后更新 `model_version` 字段
5. **A/B测试**：新旧模型并行运行，对比转化率

需要我帮你生成训练脚本和标注数据模板吗？