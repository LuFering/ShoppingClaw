## 🎯 核心结论

**JointBERT 完全满足你的需求**，它专门解决"意图识别+槽位填充"联合建模问题，比当前方案更适合电商场景。

---

## 一、当前方案 vs JointBERT 对比

### **当前方案缺陷**

```python
# 现状：两阶段分离
1. BERT分类器 → 输出 business_intent (7类)
2. 规则引擎 → 提取 slots (正则匹配)

问题：
- 意图和槽位无关联（不知道"product_recommend"需要哪些槽位）
- 无法处理子意图（只有主意图，没有"single_product"/"comparison"细分）
- 规则提取准确率低（"3000元"能提取，"三千块"就失效）
```


### **JointBERT 优势**

```
输入: "推荐一款3000元左右的华为手机"
         ↓
    JointBERT 模型
         ↓
    ┌────┴────┐
    ↓         ↓
意图分类    序列标注
product_rec  B-brand I-brand B-price I-price I-price B-category I-category
    ↓         ↓
输出: {
  "intent": "product_recommend",
  "sub_intent": "single_product",  ← 支持子意图
  "slots": {
    "brand": ["华为"],
    "budget_max": 3000,
    "category": "手机"
  }
}
```


**关键特性**：
1. **联合训练**：意图分类 + 槽位标注共享BERT编码器，互相增强
2. **端到端**：一次推理同时输出意图和槽位，无需规则后处理
3. **支持层级**：可扩展为 `主意图 → 子意图 → 槽位` 三级结构

---

## 二、JointBERT 架构设计

### **模型输入输出**

```python
# 输入
text = "推荐一款3000元的华为手机"

# JointBERT 内部结构
BERT Encoder
    ↓
    ├─ [CLS] token → Intent Classification Head → softmax → 意图概率分布
    └─ Token embeddings → Slot Tagging Head → CRF → BIO标签序列

# 输出
{
  "main_intent": "product_recommend",      # 主意图
  "sub_intent": "single_product",          # 子意图（新增）
  "slots": {                               # 槽位（自动提取）
    "category": {"value": "手机", "start": 9, "end": 11},
    "brand": {"value": "华为", "start": 7, "end": 9},
    "budget_max": {"value": 3000, "start": 4, "end": 7}
  },
  "confidence": 0.92
}
```


---

## 三、针对你业务的意图体系设计

### **三层树状结构**

```yaml
# 主意图 (7类)
product_recommend:
  sub_intents:
    - single_product:      # 单商品推荐
      required_slots: [category, budget_max]
      optional_slots: [brand, usage_scenario]
    
    - multi_product:       # 多商品对比
      required_slots: [category, budget_min, budget_max]
      optional_slots: [brands, comparison_dimensions]

product_comparison:
  sub_intents:
    - direct_compare:      # A vs B 直接对比
      required_slots: [product_a, product_b]
      optional_slots: [dimensions]
    
    - category_compare:    # 品类内对比
      required_slots: [category, budget_range]
      optional_slots: [brands]

order_query:
  sub_intents:
    - status_check:        # 查询状态
      required_slots: [order_id]
      optional_slots: [phone_number]
    
    - logistics_track:     # 物流追踪
      required_slots: [order_id]
      optional_slots: []

after_sales:
  sub_intents:
    - return_request:      # 退货
      required_slots: [order_id, reason]
      optional_slots: []
    
    - repair_request:      # 维修
      required_slots: [order_id, issue_type]
      optional_slots: []

price_check:               # 价格咨询（无子意图）
store_search:              # 店铺搜索（无子意图）
unknown:                   # 兜底
```


---

## 四、JointBERT 实现方案

### **Step 1: 安装依赖**

```bash
uv pip install transformers seqeval torch
```


---

### **Step 2: 准备标注数据**

创建文件：`data/joint_intent/train.jsonl`

```jsonl
{
  "text": "推荐一款3000元的华为手机",
  "main_intent": "product_recommend",
  "sub_intent": "single_product",
  "slots": [
    {"entity": "budget_max", "start": 4, "end": 7, "value": "3000"},
    {"entity": "brand", "start": 8, "end": 10, "value": "华为"},
    {"entity": "category", "start": 10, "end": 12, "value": "手机"}
  ]
}
{
  "text": "iPhone 15和小米14哪个好",
  "main_intent": "product_comparison",
  "sub_intent": "direct_compare",
  "slots": [
    {"entity": "product_a", "start": 0, "end": 9, "value": "iPhone 15"},
    {"entity": "product_b", "start": 10, "end": 14, "value": "小米14"}
  ]
}
{
  "text": "订单SO_12345到哪了",
  "main_intent": "order_query",
  "sub_intent": "status_check",
  "slots": [
    {"entity": "order_id", "start": 2, "end": 10, "value": "SO_12345"}
  ]
}
```


**标注规范**：
- `start/end`：字符级位置（Python切片 `[start:end]`）
- `entity`：槽位类型（对应Schema定义）
- 每个样本必须有 `main_intent` + `sub_intent`

---

### **Step 3: JointBERT 模型实现**

创建文件：`src/services/joint_intent_model.py`

```python
import torch
import torch.nn as nn
from transformers import BertModel, BertTokenizer
from typing import Dict, List, Tuple

class JointIntentSlotModel(nn.Module):
    """JointBERT：意图分类 + 槽位填充联合模型"""
    
    def __init__(
        self,
        bert_model_name: str = "hfl/chinese-roberta-wwm-ext",
        num_main_intents: int = 7,
        num_sub_intents: int = 10,  # 所有子意图总数
        num_slot_labels: int = 15   # BIO标签数（5个槽位×3=15）
    ):
        super().__init__()
        
        # BERT编码器
        self.bert = BertModel.from_pretrained(bert_model_name)
        hidden_size = self.bert.config.hidden_size
        
        # 意图分类头（主意图）
        self.main_intent_classifier = nn.Sequential(
            nn.Linear(hidden_size, hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_size // 2, num_main_intents)
        )
        
        # 子意图分类头（依赖主意图[CLS]向量）
        self.sub_intent_classifier = nn.Sequential(
            nn.Linear(hidden_size + num_main_intents, hidden_size // 2),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_size // 2, num_sub_intents)
        )
        
        # 槽位标注头（每个token的BIO标签）
        self.slot_tagger = nn.Linear(hidden_size, num_slot_labels)
        
        # CRF层（可选，提升序列标注一致性）
        # from pytorch_crf import CRF
        # self.crf = CRF(num_slot_labels, batch_first=True)
    
    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: torch.Tensor,
        main_intent_labels: torch.Tensor = None,
        sub_intent_labels: torch.Tensor = None,
        slot_labels: torch.Tensor = None
    ) -> Dict[str, torch.Tensor]:
        """
        Args:
            input_ids: [batch_size, seq_len]
            attention_mask: [batch_size, seq_len]
            main_intent_labels: [batch_size] (训练时传入)
            sub_intent_labels: [batch_size] (训练时传入)
            slot_labels: [batch_size, seq_len] (训练时传入，BIO标签)
        
        Returns:
            {
                "main_intent_logits": [batch_size, num_main_intents],
                "sub_intent_logits": [batch_size, num_sub_intents],
                "slot_logits": [batch_size, seq_len, num_slot_labels],
                "loss": scalar (训练时计算)
            }
        """
        # BERT编码
        outputs = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        sequence_output = outputs.last_hidden_state  # [batch, seq_len, hidden]
        cls_output = outputs.pooler_output             # [batch, hidden]
        
        # 1. 主意图分类
        main_intent_logits = self.main_intent_classifier(cls_output)
        
        # 2. 子意图分类（拼接主意图概率作为特征）
        if main_intent_labels is not None:
            # 训练时：使用真实标签one-hot
            main_intent_onehot = torch.zeros_like(main_intent_logits).scatter_(
                1, main_intent_labels.unsqueeze(1), 1
            )
        else:
            # 推理时：使用预测概率
            main_intent_onehot = torch.softmax(main_intent_logits, dim=-1)
        
        sub_intent_input = torch.cat([cls_output, main_intent_onehot], dim=-1)
        sub_intent_logits = self.sub_intent_classifier(sub_intent_input)
        
        # 3. 槽位标注
        slot_logits = self.slot_tagger(sequence_output)  # [batch, seq_len, num_labels]
        
        # 4. 计算损失（训练时）
        loss = None
        if main_intent_labels is not None:
            intent_loss = nn.CrossEntropyLoss()(main_intent_logits, main_intent_labels)
            sub_intent_loss = nn.CrossEntropyLoss()(sub_intent_logits, sub_intent_labels)
            
            # 槽位损失（简化版：CrossEntropy，实际应用CRF）
            slot_loss = nn.CrossEntropyLoss()(
                slot_logits.view(-1, slot_logits.size(-1)),
                slot_labels.view(-1)
            )
            
            # 加权求和
            loss = intent_loss + 0.5 * sub_intent_loss + 0.3 * slot_loss
        
        return {
            "main_intent_logits": main_intent_logits,
            "sub_intent_logits": sub_intent_logits,
            "slot_logits": slot_logits,
            "loss": loss
        }
```


---

### **Step 4: 数据预处理**

创建文件：`scripts/prepare_joint_data.py`

```python
import json
from transformers import BertTokenizer
import torch

# 标签映射
MAIN_INTENT_MAP = {
    "product_recommend": 0,
    "product_comparison": 1,
    "order_query": 2,
    "after_sales": 3,
    "price_check": 4,
    "store_search": 5,
    "unknown": 6
}

SUB_INTENT_MAP = {
    "single_product": 0,
    "multi_product": 1,
    "direct_compare": 2,
    "category_compare": 3,
    "status_check": 4,
    "logistics_track": 5,
    "return_request": 6,
    "repair_request": 7,
    "chitchat": 8,
    "clarify": 9
}

# 槽位BIO标签（5种槽位 × 3标签 = 15类）
SLOT_TAGS = [
    "O",  # 0: 非实体
    "B-category", "I-category",  # 1-2: 品类
    "B-brand", "I-brand",        # 3-4: 品牌
    "B-budget_max", "I-budget_max",  # 5-6: 预算上限
    "B-order_id", "I-order_id",  # 7-8: 订单号
    "B-product_a", "I-product_a",  # 9-10: 商品A
    "B-product_b", "I-product_b",  # 11-12: 商品B
    "B-reason", "I-reason"       # 13-14: 原因
]
SLOT_TAG_MAP = {tag: idx for idx, tag in enumerate(SLOT_TAGS)}

def convert_to_biolabels(text: str, slots: list) -> list:
    """将槽位转换为BIO标签序列"""
    labels = ["O"] * len(text)
    
    for slot in slots:
        entity = slot["entity"]
        start = slot["start"]
        end = slot["end"]
        
        # B标签
        labels[start] = f"B-{entity}"
        # I标签
        for i in range(start + 1, end):
            labels[i] = f"I-{entity}"
    
    return [SLOT_TAG_MAP.get(label, 0) for label in labels]

def prepare_dataset(file_path: str, tokenizer, max_len=128):
    """准备JointBERT训练数据"""
    input_ids_list = []
    attention_masks_list = []
    main_intent_labels = []
    sub_intent_labels = []
    slot_labels_list = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            item = json.loads(line)
            text = item["text"]
            
            # Tokenize
            encoded = tokenizer(
                text,
                padding="max_length",
                truncation=True,
                max_length=max_len,
                return_tensors="pt"
            )
            
            # 转换标签
            main_label = MAIN_INTENT_MAP[item["main_intent"]]
            sub_label = SUB_INTENT_MAP[item["sub_intent"]]
            slot_bio = convert_to_biolabels(text, item["slots"])
            
            # 对齐slot标签到token级别（简化处理）
            slot_label_tensor = torch.zeros(max_len, dtype=torch.long)
            for i, label in enumerate(slot_bio[:max_len]):
                slot_label_tensor[i] = label
            
            input_ids_list.append(encoded["input_ids"].squeeze())
            attention_masks_list.append(encoded["attention_mask"].squeeze())
            main_intent_labels.append(main_label)
            sub_intent_labels.append(sub_label)
            slot_labels_list.append(slot_label_tensor)
    
    return {
        "input_ids": torch.stack(input_ids_list),
        "attention_mask": torch.stack(attention_masks_list),
        "main_intent_labels": torch.tensor(main_intent_labels),
        "sub_intent_labels": torch.tensor(sub_intent_labels),
        "slot_labels": torch.stack(slot_labels_list)
    }

# 使用示例
tokenizer = BertTokenizer.from_pretrained("hfl/chinese-roberta-wwm-ext")
train_data = prepare_dataset("data/joint_intent/train.jsonl", tokenizer)
print(f"训练样本数: {len(train_data['input_ids'])}")
```


---

### **Step 5: 训练脚本**

创建文件：`scripts/train_joint_bert.py`

```python
import torch
from torch.utils.data import DataLoader, TensorDataset
from src.services.joint_intent_model import JointIntentSlotModel
from scripts.prepare_joint_data import prepare_dataset
from transformers import BertTokenizer

# ==================== 1. 加载数据 ====================
tokenizer = BertTokenizer.from_pretrained("hfl/chinese-roberta-wwm-ext")
train_data = prepare_dataset("data/joint_intent/train.jsonl", tokenizer)

dataset = TensorDataset(
    train_data["input_ids"],
    train_data["attention_mask"],
    train_data["main_intent_labels"],
    train_data["sub_intent_labels"],
    train_data["slot_labels"]
)
dataloader = DataLoader(dataset, batch_size=16, shuffle=True)

# ==================== 2. 初始化模型 ====================
model = JointIntentSlotModel(
    bert_model_name="hfl/chinese-roberta-wwm-ext",
    num_main_intents=7,
    num_sub_intents=10,
    num_slot_labels=15
)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model.to(device)

# ==================== 3. 优化器 ====================
optimizer = torch.optim.AdamW(model.parameters(), lr=2e-5)

# ==================== 4. 训练循环 ====================
num_epochs = 3
for epoch in range(num_epochs):
    model.train()
    total_loss = 0
    
    for batch in dataloader:
        input_ids, attention_mask, main_labels, sub_labels, slot_labels = [
            b.to(device) for b in batch
        ]
        
        optimizer.zero_grad()
        outputs = model(
            input_ids=input_ids,
            attention_mask=attention_mask,
            main_intent_labels=main_labels,
            sub_intent_labels=sub_labels,
            slot_labels=slot_labels
        )
        
        loss = outputs["loss"]
        loss.backward()
        optimizer.step()
        
        total_loss += loss.item()
    
    avg_loss = total_loss / len(dataloader)
    print(f"Epoch {epoch+1}/{num_epochs}, Loss: {avg_loss:.4f}")

# ==================== 5. 保存模型 ====================
torch.save(model.state_dict(), "./model/joint_intent_bert.pth")
tokenizer.save_pretrained("./model/joint_intent_bert")
print("✅ JointBERT 训练完成！")
```


---

### **Step 6: 推理服务封装**

修改文件：`src/services/intent_service.py`（替换原有实现）

```python
import torch
from src.services.joint_intent_model import JointIntentSlotModel
from transformers import BertTokenizer
from agents.common.model import IntentResult, SlotInfo


class JointIntentService:
    """基于JointBERT的意图识别服务"""

    def __init__(self, model_path: str = "./model/joint_intent_bert.pth"):
        self.tokenizer = BertTokenizer.from_pretrained("hfl/chinese-roberta-wwm-ext")

        self.model = JointIntentSlotModel(
            num_main_intents=7,
            num_sub_intents=10,
            num_slot_labels=15
        )
        self.model.load_state_dict(torch.load(model_path, map_location="cpu"))
        self.model.eval()

        # 反向映射
        self.MAIN_INTENTS = ["product_recommend", "product_comparison", ...]
        self.SUB_INTENTS = ["single_product", "multi_product", ...]
        self.SLOT_TAGS = ["O", "B-category", "I-category", ...]

    def recognize_intent(self, user_input: str) -> IntentResult:
        """端到端意图识别"""
        # Tokenize
        encoded = self.tokenizer(
            user_input,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=128
        )

        # 推理
        with torch.no_grad():
            outputs = self.model(
                input_ids=encoded["input_ids"],
                attention_mask=encoded["attention_mask"]
            )

        # 解析主意图
        main_intent_idx = torch.argmax(outputs["main_intent_logits"], dim=-1).item()
        main_intent = self.MAIN_INTENTS[main_intent_idx]
        main_confidence = torch.softmax(outputs["main_intent_logits"], dim=-1)[0][main_intent_idx].item()

        # 解析子意图
        sub_intent_idx = torch.argmax(outputs["sub_intent_logits"], dim=-1).item()
        sub_intent = self.SUB_INTENTS[sub_intent_idx]

        # 解析槽位（从BIO标签提取）
        slot_logits = outputs["slot_logits"][0]  # [seq_len, num_labels]
        slot_preds = torch.argmax(slot_logits, dim=-1).tolist()
        slots = self._extract_slots_from_bio(user_input, slot_preds)

        # 构建结果
        return IntentResult(
            raw_input=user_input,
            business_intent=main_intent,
            sub_intent=sub_intent,
            slots=slots,
            missing_slots=self._get_missing_slots(main_intent, sub_intent, slots),
            intent_confidence=main_confidence,
            clarification_needed=main_confidence < 0.6,
            model_version="joint_bert_v1.0"
        )

    def _extract_slots_from_bio(self, text: str, bio_labels: list) -> dict:
        """从BIO标签序列提取槽位"""
        slots = {}
        current_entity = None
        current_start = None
        current_value = []

        for i, label_idx in enumerate(bio_labels):
            if i >= len(text):
                break

            label = self.SLOT_TAGS[label_idx]

            if label.startswith("B-"):
                # 保存上一个实体
                if current_entity:
                    slots[current_entity] = SlotInfo(
                        value="".join(current_value),
                        source="user_input"
                    )

                # 开始新实体
                current_entity = label[2:]
                current_start = i
                current_value = [text[i]]

            elif label.startswith("I-") and current_entity:
                current_value.append(text[i])

            else:
                # O标签，结束当前实体
                if current_entity:
                    slots[current_entity] = SlotInfo(
                        value="".join(current_value),
                        source="user_input"
                    )
                    current_entity = None
                    current_value = []

        # 处理最后一个实体
        if current_entity:
            slots[current_entity] = SlotInfo(
                value="".join(current_value),
                source="user_input"
            )

        return slots
```


---

## 五、回答你的核心问题

### **Q1: 训练模型只传意图标签吗？**

**答**：JointBERT 传3类标签：
```python
{
  "main_intent_labels": [0, 1, 2, ...],      # 主意图ID
  "sub_intent_labels": [0, 3, 5, ...],       # 子意图ID
  "slot_labels": [[0,1,2,0,3,4,...], ...]    # 每个token的BIO标签
}
```


### **Q2: BERT必须传意图标签吗？**

**答**：
- **预训练阶段**：不需要（MLM任务）
- **微调阶段**：必须传（监督学习）
- **推理阶段**：不传（模型预测）

### **Q3: 有子意图要改模型吗？**

**答**：**是的**，当前单头分类器不支持子意图，必须升级为JointBERT或多头架构。

### **Q4: JointBERT能满足需求吗？**

**答**：**完美匹配**，它的设计目标就是：
- ✅ 主意图 + 子意图联合分类
- ✅ 意图与槽位联合建模（互相增强）
- ✅ 端到端提取，无需规则后处理

---

## 六、立即行动清单

1. **设计意图体系**：确定主意图7类 + 子意图10类 + 槽位5种
2. **标注数据**：准备3500+条标注样本（`train.jsonl`）
3. **实现JointBERT**：复制上述 `joint_intent_model.py`
4. **训练模型**：执行 `train_joint_bert.py`
5. **替换服务**：用 `JointIntentService` 替换原 `IntentService`
6. **测试验证**：在PyCharm Debugger中观察 `IntentResult` 输出

需要我生成完整的标注数据模板和训练配置吗？