分三个层次来回答：**意图体系设计 → 训练流程 → 插入 Agent 的方式**。每一层都直接对应你引用的需求条目。

---

## 一、意图体系设计（对应"意图分层设计"需求）

先把电商导购场景的完整树状结构确定下来，训练数据和模型结构都必须基于这张表，不能事后再改。

```
主意图 (7类)
├── product_recommend          商品推荐
│   ├── sub: single_product    slots: [category*, budget_max, brand, usage_scenario]
│   └── sub: multi_compare     slots: [category*, budget_min, budget_max, brands]
│
├── product_comparison         商品对比
│   ├── sub: direct_compare    slots: [product_a*, product_b*]
│   └── sub: category_compare  slots: [category*, budget_range]
│
├── order_query                订单查询
│   ├── sub: status_check      slots: [order_id*]
│   └── sub: logistics_track   slots: [order_id*]
│
├── after_sales                售后咨询
│   ├── sub: return_request    slots: [order_id*, reason]
│   └── sub: repair_request    slots: [order_id*, issue_type]
│
├── price_check                价格咨询     slots: [category*, brand]
├── store_search               店铺搜索     slots: [brand*, category]
└── unknown                    兜底意图     slots: []

* 号 = 必填槽位
```

这张表在代码里有唯一的存放位置：

```python
# src/agents/common/middleware/intent_schema.py
# 整个系统的意图体系唯一来源，训练脚本、推理服务、Middleware 全部 import 这里

INTENT_SCHEMA = {
    "product_recommend": {
        "sub_intents": {
            "single_product":  {"required": ["category"], "optional": ["budget_max", "brand", "usage_scenario"]},
            "multi_compare":   {"required": ["category"], "optional": ["budget_min", "budget_max", "brands"]},
        }
    },
    "product_comparison": {
        "sub_intents": {
            "direct_compare":  {"required": ["product_a", "product_b"], "optional": ["dimensions"]},
            "category_compare":{"required": ["category"], "optional": ["budget_range", "brands"]},
        }
    },
    "order_query": {
        "sub_intents": {
            "status_check":    {"required": ["order_id"], "optional": ["phone_number"]},
            "logistics_track": {"required": ["order_id"], "optional": []},
        }
    },
    "after_sales": {
        "sub_intents": {
            "return_request":  {"required": ["order_id", "reason"], "optional": []},
            "repair_request":  {"required": ["order_id", "issue_type"], "optional": []},
        }
    },
    "price_check":   {"sub_intents": None, "required": ["category"], "optional": ["brand"]},
    "store_search":  {"sub_intents": None, "required": ["brand"],    "optional": ["category"]},
    "unknown":       {"sub_intents": None, "required": [],           "optional": []},
}

# 所有标签的枚举，训练和推理共用，顺序不能改
MAIN_INTENTS = list(INTENT_SCHEMA.keys())  # 顺序固定

SUB_INTENTS = ["single_product", "multi_compare", "direct_compare", "category_compare",
               "status_check", "logistics_track", "return_request", "repair_request",
               "none"]  # "none" 代表无子意图

SLOT_TAGS = [
    "O",
    "B-category",    "I-category",
    "B-brand",       "I-brand",
    "B-budget_max",  "I-budget_max",
    "B-budget_min",  "I-budget_min",
    "B-product_a",   "I-product_a",
    "B-product_b",   "I-product_b",
    "B-order_id",    "I-order_id",
    "B-reason",      "I-reason",
    "B-issue_type",  "I-issue_type",
]

MAIN_INTENT2ID = {v: i for i, v in enumerate(MAIN_INTENTS)}
SUB_INTENT2ID  = {v: i for i, v in enumerate(SUB_INTENTS)}
SLOT_TAG2ID    = {v: i for i, v in enumerate(SLOT_TAGS)}
ID2MAIN_INTENT = {i: v for v, i in MAIN_INTENT2ID.items()}
ID2SUB_INTENT  = {i: v for v, i in SUB_INTENT2ID.items()}
ID2SLOT_TAG    = {i: v for v, i in SLOT_TAG2ID.items()}

# 主意图 → 合法子意图集合（推理时掩码用）
VALID_SUB_INTENTS = {
    "product_recommend":  {"single_product", "multi_compare"},
    "product_comparison": {"direct_compare", "category_compare"},
    "order_query":        {"status_check", "logistics_track"},
    "after_sales":        {"return_request", "repair_request"},
    "price_check":        {"none"},
    "store_search":       {"none"},
    "unknown":            {"none"},
}

# 主意图 → 必填槽位（推理时缺失槽位计算用）
def get_required_slots(main_intent: str, sub_intent: str | None) -> list[str]:
    schema = INTENT_SCHEMA.get(main_intent, {})
    if schema.get("sub_intents") and sub_intent and sub_intent != "none":
        return schema["sub_intents"].get(sub_intent, {}).get("required", [])
    return schema.get("required", [])
```

---

## 二、训练流程

### 2.1 数据标注规范

每条数据的格式：

```jsonl
{
  "text": "帮我找一款4000以内的华为手机",
  "main_intent": "product_recommend",
  "sub_intent": "single_product",
  "slots": [
    {"entity": "budget_max", "start": 6,  "end": 10, "value": "4000"},
    {"entity": "brand",      "start": 12, "end": 14, "value": "华为"},
    {"entity": "category",   "start": 14, "end": 16, "value": "手机"}
  ]
}
```

数量要求：主意图每类最少 500 条，`unknown` 类用"不知道怎么问的句子"填充，不少于 200 条。数据越多越好，上限通常在 10000 条以上效果才趋于稳定。

没有数据的冷启动期，先用 GPT/Qwen 批量生成带多样性表达的伪标注数据，经人工抽样校验 10% 后再训练。

### 2.2 数据预处理（修复 token 对齐 Bug）

```python
# scripts/prepare_joint_data.py
import json
from transformers import BertTokenizer
import torch
from src.agents.common.middleware.intent_schema import (
    MAIN_INTENT2ID, SUB_INTENT2ID, SLOT_TAG2ID
)

def build_token_labels(text: str, char_slots: list, tokenizer) -> list[int]:
    """
    将字符级槽位标注对齐到 token 级别。
    关键：用 offset_mapping 做字符→token 的映射，不能直接用字符下标。
    """
    encoding = tokenizer(
        text,
        return_offsets_mapping=True,
        add_special_tokens=True,
    )
    offsets = encoding["offset_mapping"]  # [(char_start, char_end), ...]

    # 先建字符级标签数组
    char_labels = ["O"] * len(text)
    for slot in char_slots:
        entity = slot["entity"]
        s, e = slot["start"], slot["end"]
        char_labels[s] = f"B-{entity}"
        for i in range(s + 1, e):
            char_labels[i] = f"I-{entity}"

    # 再映射到 token 级别
    token_labels = []
    for char_start, char_end in offsets:
        if char_start == char_end:
            # 特殊 token（[CLS]/[SEP]/[PAD]），忽略梯度
            token_labels.append(-100)
        else:
            token_labels.append(SLOT_TAG2ID.get(char_labels[char_start], 0))

    return token_labels


def prepare_dataset(file_path: str, tokenizer, max_len: int = 128) -> dict:
    input_ids_list, attention_masks_list = [], []
    main_labels, sub_labels, slot_labels_list = [], [], []

    with open(file_path, encoding="utf-8") as f:
        for line in f:
            item = json.loads(line.strip())
            text = item["text"]

            encoding = tokenizer(
                text,
                padding="max_length",
                truncation=True,
                max_length=max_len,
                return_offsets_mapping=True,
            )

            token_slot_labels = build_token_labels(text, item["slots"], tokenizer)
            # padding 到 max_len
            pad_len = max_len - len(token_slot_labels)
            token_slot_labels = token_slot_labels[:max_len] + [-100] * pad_len

            input_ids_list.append(torch.tensor(encoding["input_ids"]))
            attention_masks_list.append(torch.tensor(encoding["attention_mask"]))
            main_labels.append(MAIN_INTENT2ID[item["main_intent"]])
            sub_labels.append(SUB_INTENT2ID[item["sub_intent"]])
            slot_labels_list.append(torch.tensor(token_slot_labels))

    return {
        "input_ids":           torch.stack(input_ids_list),
        "attention_mask":      torch.stack(attention_masks_list),
        "main_intent_labels":  torch.tensor(main_labels),
        "sub_intent_labels":   torch.tensor(sub_labels),
        "slot_labels":         torch.stack(slot_labels_list),
    }
```

### 2.3 模型定义

```python
# src/services/joint_intent_model.py
import torch
import torch.nn as nn
from transformers import BertModel
from src.agents.common.middleware.intent_schema import (
    MAIN_INTENTS, SUB_INTENTS, SLOT_TAGS
)

class JointIntentSlotModel(nn.Module):

    def __init__(self, bert_model_name: str = "hfl/chinese-roberta-wwm-ext"):
        super().__init__()
        self.bert = BertModel.from_pretrained(bert_model_name)
        hidden = self.bert.config.hidden_size  # 768

        n_main  = len(MAIN_INTENTS)
        n_sub   = len(SUB_INTENTS)
        n_slot  = len(SLOT_TAGS)

        # 主意图头
        self.main_clf = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden, n_main),
        )

        # 子意图头：拼接 [CLS] 向量 + 主意图 softmax 概率
        self.sub_clf = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden + n_main, hidden // 2),
            nn.GELU(),
            nn.Linear(hidden // 2, n_sub),
        )

        # 槽位序列标注头
        self.slot_clf = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden, n_slot),
        )

    def forward(
        self,
        input_ids:           torch.Tensor,
        attention_mask:      torch.Tensor,
        main_intent_labels:  torch.Tensor | None = None,
        sub_intent_labels:   torch.Tensor | None = None,
        slot_labels:         torch.Tensor | None = None,
    ) -> dict:
        out = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        seq_out = out.last_hidden_state   # [B, L, H]
        cls_out = out.pooler_output       # [B, H]

        # 主意图
        main_logits = self.main_clf(cls_out)                          # [B, n_main]

        # 子意图：用真实主意图（训练）或预测概率（推理）拼接
        if main_intent_labels is not None:
            main_onehot = torch.zeros_like(main_logits).scatter_(
                1, main_intent_labels.unsqueeze(1), 1.0
            )
        else:
            main_onehot = torch.softmax(main_logits, dim=-1).detach()
        sub_logits = self.sub_clf(torch.cat([cls_out, main_onehot], dim=-1))  # [B, n_sub]

        # 槽位
        slot_logits = self.slot_clf(seq_out)                          # [B, L, n_slot]

        result = {
            "main_intent_logits": main_logits,
            "sub_intent_logits":  sub_logits,
            "slot_logits":        slot_logits,
        }

        if main_intent_labels is not None:
            # 损失权重经验值：主意图最重要，三者等权或略微调整
            loss_main = nn.CrossEntropyLoss()(main_logits, main_intent_labels)
            loss_sub  = nn.CrossEntropyLoss()(sub_logits,  sub_intent_labels)
            loss_slot = nn.CrossEntropyLoss(ignore_index=-100)(  # -100 忽略特殊 token
                slot_logits.view(-1, slot_logits.size(-1)),
                slot_labels.view(-1),
            )
            result["loss"] = loss_main + loss_sub + loss_slot  # 1:1:1 等权，比拍脑袋的 0.3 更合理

        return result
```

### 2.4 训练脚本

```python
# scripts/train_joint_bert.py
import torch
from torch.utils.data import DataLoader, TensorDataset, random_split
from transformers import BertTokenizer, get_linear_schedule_with_warmup
from seqeval.metrics import f1_score as seq_f1
import numpy as np
from src.services.joint_intent_model import JointIntentSlotModel
from scripts.prepare_joint_data import prepare_dataset
from src.agents.common.middleware.intent_schema import (
    ID2MAIN_INTENT, ID2SUB_INTENT, ID2SLOT_TAG, MAIN_INTENTS, SUB_INTENTS
)

# ── 配置 ──────────────────────────────────────────────────
BERT_NAME  = "hfl/chinese-roberta-wwm-ext"
DATA_FILE  = "data/joint_intent/train.jsonl"
MODEL_DIR  = "./model/joint_intent_bert"
BATCH_SIZE = 16
EPOCHS     = 5
LR         = 2e-5
MAX_LEN    = 128
# ──────────────────────────────────────────────────────────

tokenizer = BertTokenizer.from_pretrained(BERT_NAME)
data      = prepare_dataset(DATA_FILE, tokenizer, MAX_LEN)

dataset   = TensorDataset(
    data["input_ids"], data["attention_mask"],
    data["main_intent_labels"], data["sub_intent_labels"],
    data["slot_labels"],
)
val_size  = max(int(len(dataset) * 0.15), 1)
train_ds, val_ds = random_split(dataset, [len(dataset) - val_size, val_size])

train_dl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
val_dl   = DataLoader(val_ds,   batch_size=32)

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
model  = JointIntentSlotModel(BERT_NAME).to(device)

optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
total_steps = len(train_dl) * EPOCHS
scheduler = get_linear_schedule_with_warmup(
    optimizer,
    num_warmup_steps=total_steps // 10,
    num_training_steps=total_steps,
)


def evaluate(model, loader):
    model.eval()
    main_correct = sub_correct = total = 0
    all_true_slots, all_pred_slots = [], []

    with torch.no_grad():
        for batch in loader:
            ids, mask, main_lbl, sub_lbl, slot_lbl = [b.to(device) for b in batch]
            out = model(input_ids=ids, attention_mask=mask)

            main_pred = out["main_intent_logits"].argmax(-1)
            sub_pred  = out["sub_intent_logits"].argmax(-1)
            slot_pred = out["slot_logits"].argmax(-1)

            main_correct += (main_pred == main_lbl).sum().item()
            sub_correct  += (sub_pred  == sub_lbl).sum().item()
            total        += main_lbl.size(0)

            # 槽位：还原为标签字符串，计算实体级 F1
            for true_seq, pred_seq in zip(slot_lbl.cpu().tolist(), slot_pred.cpu().tolist()):
                t = [ID2SLOT_TAG.get(l, "O") for l in true_seq if l != -100]
                p = [ID2SLOT_TAG.get(p, "O") for p, l in zip(pred_seq, true_seq) if l != -100]
                all_true_slots.append(t)
                all_pred_slots.append(p)

    slot_f1 = seq_f1(all_true_slots, all_pred_slots, zero_division=0)
    return {
        "main_acc": main_correct / total,
        "sub_acc":  sub_correct  / total,
        "slot_f1":  slot_f1,
    }


best_slot_f1 = 0.0
for epoch in range(EPOCHS):
    model.train()
    for batch in train_dl:
        ids, mask, main_lbl, sub_lbl, slot_lbl = [b.to(device) for b in batch]
        out  = model(ids, mask, main_lbl, sub_lbl, slot_lbl)
        loss = out["loss"]
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()
        scheduler.step()
        optimizer.zero_grad()

    metrics = evaluate(model, val_dl)
    print(f"Epoch {epoch+1} | main_acc={metrics['main_acc']:.3f} "
          f"sub_acc={metrics['sub_acc']:.3f} slot_f1={metrics['slot_f1']:.3f}")

    if metrics["slot_f1"] > best_slot_f1:
        best_slot_f1 = metrics["slot_f1"]
        import os, json
        os.makedirs(MODEL_DIR, exist_ok=True)
        torch.save(model.state_dict(), f"{MODEL_DIR}/model.pth")
        tokenizer.save_pretrained(MODEL_DIR)
        # 把标签映射一起存进去，推理时从这里读，不硬编码
        json.dump({
            "main_intents": MAIN_INTENTS,
            "sub_intents":  SUB_INTENTS,
        }, open(f"{MODEL_DIR}/label_config.json", "w", encoding="utf-8"),
        ensure_ascii=False, indent=2)
        print(f"  → 保存最优模型 (slot_f1={best_slot_f1:.3f})")

print("训练完成")
```

---

## 三、插入 Agent 的完整方式

这是把上面所有东西连接起来的部分，对应"兜底策略"和"澄清话术"需求。

### 3.1 推理服务

```python
# src/services/intent_service.py
import json, asyncio, torch
from transformers import BertTokenizer
from src.services.joint_intent_model import JointIntentSlotModel
from src.agents.common.middleware.intent_schema import (
    VALID_SUB_INTENTS, get_required_slots,
    ID2MAIN_INTENT, ID2SUB_INTENT, ID2SLOT_TAG
)

class JointIntentService:
    """单例，应用启动时初始化，推理时不重复加载"""

    def __init__(self, model_dir: str = "./model/joint_intent_bert"):
        cfg = json.load(open(f"{model_dir}/label_config.json"))
        self._main_intents = cfg["main_intents"]
        self._sub_intents  = cfg["sub_intents"]

        self._tokenizer = BertTokenizer.from_pretrained(model_dir)
        self._model     = JointIntentSlotModel()
        self._model.load_state_dict(
            torch.load(f"{model_dir}/model.pth", map_location="cpu")
        )
        self._model.eval()
        # 有 GPU 就用
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)

    def predict(self, text: str, confidence_threshold: float = 0.6) -> dict:
        enc = self._tokenizer(
            text, return_tensors="pt",
            truncation=True, max_length=128,
            return_offsets_mapping=True,
        )
        offsets = enc.pop("offset_mapping")
        enc = {k: v.to(self._device) for k, v in enc.items()}

        with torch.no_grad():
            out = self._model(**enc)

        # ── 主意图 ────────────────────────────────────────
        main_probs = torch.softmax(out["main_intent_logits"], dim=-1)[0].cpu()
        main_idx   = main_probs.argmax().item()
        main_conf  = main_probs[main_idx].item()
        main_intent = self._main_intents[main_idx]

        # ── 子意图（只在合法子意图里取最大值）──────────────
        sub_probs  = torch.softmax(out["sub_intent_logits"], dim=-1)[0].cpu()
        valid_subs = VALID_SUB_INTENTS.get(main_intent, {"none"})
        for i, name in enumerate(self._sub_intents):
            if name not in valid_subs:
                sub_probs[i] = -1e9
        sub_idx    = sub_probs.argmax().item()
        sub_intent = self._sub_intents[sub_idx]
        if sub_intent == "none":
            sub_intent = None

        # ── 槽位（BIO 解码，对齐回原始字符）─────────────────
        slot_preds = out["slot_logits"][0].argmax(-1).cpu().tolist()
        slots = self._decode_slots(text, slot_preds, offsets[0].tolist())

        # ── 缺失槽位 ──────────────────────────────────────
        required     = get_required_slots(main_intent, sub_intent)
        missing_slots = [s for s in required if s not in slots]

        return {
            "raw_input":           text,
            "main_intent":         main_intent,
            "sub_intent":          sub_intent,
            "slots":               slots,
            "missing_slots":       missing_slots,
            "intent_confidence":   round(main_conf, 4),
            "clarification_needed": main_conf < confidence_threshold,
        }

    def _decode_slots(self, text: str, token_preds: list, offsets: list) -> dict:
        slots = {}
        current_entity, current_chars = None, []

        for pred_id, (char_s, char_e) in zip(token_preds, offsets):
            if char_s == char_e:   # 特殊 token，跳过
                continue
            tag = ID2SLOT_TAG.get(pred_id, "O")

            if tag.startswith("B-"):
                if current_entity:
                    slots[current_entity] = "".join(current_chars)
                current_entity = tag[2:]
                current_chars  = [text[char_s:char_e]]

            elif tag.startswith("I-") and current_entity == tag[2:]:
                current_chars.append(text[char_s:char_e])

            else:
                if current_entity:
                    slots[current_entity] = "".join(current_chars)
                    current_entity, current_chars = None, []

        if current_entity:
            slots[current_entity] = "".join(current_chars)

        return slots


# 全局单例，和项目里 agent_manager 同级别
_intent_service: JointIntentService | None = None

def get_intent_service() -> JointIntentService:
    global _intent_service
    if _intent_service is None:
        _intent_service = JointIntentService()
    return _intent_service
```

### 3.2 Middleware（插入 Agent 的关键）

```python
# src/agents/common/middleware/intent_detector.py
import asyncio
from typing import Annotated, NotRequired
from langchain.agents.middleware.types import AgentMiddleware, AgentState, PrivateStateAttr
from langchain_core.messages import HumanMessage
from langgraph.runtime import Runtime
from src.services.intent_service import get_intent_service

class IntentDetectorState(AgentState):
    """
    注册进 LangGraph 状态机的意图字段。
    PrivateStateAttr 表示不向父 Agent 传播（子 Agent 独立识别自己的意图）。
    如果需要 MasterAgent 读取，去掉 PrivateStateAttr。
    """
    intent: NotRequired[Annotated[dict, PrivateStateAttr]]


class IntentDetectorMiddleware(AgentMiddleware):
    name = "intent_detector"
    state_schema = IntentDetectorState   # 必须有，不能是 None

    def __init__(self, confidence_threshold: float = 0.6):
        self._threshold = confidence_threshold

    # ── 同步版（兼容 factory.py 的同步调用路径）──────────────
    def before_agent(self, state: dict, runtime: Runtime) -> dict | None:
        text = self._get_last_human_text(state)
        if not text or "intent" in state:   # 已有意图就不重复识别
            return None
        intent_result = get_intent_service().predict(text, self._threshold)
        return {"intent": intent_result}

    # ── 异步版（stream_messages 走的是这个）─────────────────
    async def abefore_agent(self, state: dict, runtime: Runtime) -> dict | None:
        text = self._get_last_human_text(state)
        if not text or "intent" in state:
            return None
        # PyTorch 推理是 CPU/GPU 密集型，放进线程池不阻塞事件循环
        intent_result = await asyncio.to_thread(
            get_intent_service().predict, text, self._threshold
        )
        return {"intent": intent_result}

    @staticmethod
    def _get_last_human_text(state: dict) -> str | None:
        for msg in reversed(state.get("messages", [])):
            if isinstance(msg, HumanMessage):
                return msg.content if isinstance(msg.content, str) else None
        return None
```

### 3.3 把 Middleware 挂载到 MasterAgent（以及澄清兜底逻辑）

```python
# src/agents/master_agent/graph.py

from src.agents.common.middleware.intent_detector import IntentDetectorMiddleware
from src.agents.master_agent.agent_demo import create_master_agent

async def get_graph(self, **kwargs):
    context = self.context_schema.from_file(module_name=self.module_name)
    model   = load_chat_model(context.model)
    tools   = await self.get_tools()

    graph = create_master_agent(
        model=model,
        context_schema=MasterContext,
        tools=tools,
        middleware=[
            IntentDetectorMiddleware(confidence_threshold=0.6),  # ← 第一个执行
            PatchToolCallsMiddleware(),
            ToolCallLimitMiddleware(run_limit=10, thread_limit=20, exit_behavior="end"),
            TodoListMiddleware(),
        ],
    )
    return graph
```

### 3.4 BASE_PROMPT 里告诉 MasterAgent 如何读取和使用意图

在 `src/agents/master_agent/BASE_PROMPT.md` 里追加一节（不改原有内容）：

```markdown
## 意图状态读取规范

每轮推理开始前，你可以从 `state.intent` 读取意图识别结果，结构如下：

```json
{
  "main_intent":         "product_recommend",
  "sub_intent":          "single_product",
  "slots":               {"category": "手机", "budget_max": "4000"},
  "missing_slots":       ["category"],
  "intent_confidence":   0.87,
  "clarification_needed": false
}
```

### 使用规则

**当 `clarification_needed = true`（置信度 < 0.6）时**：
停止一切工具调用，直接向用户发起澄清，必须给出 2-3 个可能意图选项，
例如："您是想查询订单状态，还是申请退货？"
不得凭猜测调用任何 SubAgent。

**当 `missing_slots` 非空时**：
意图已明确，但必填信息缺失。优先调用工具补全，无法补全时才追问用户，
一次追问不超过 2 个槽位，提供选项而非开放式问题。

**当 `main_intent = "unknown"` 时**：
直接触发兜底话术："我可以帮您推荐商品、查询订单或联系售后，请问您需要哪方面的帮助？"
不得调用任何 SubAgent。

**置信度 0.6-0.75 的灰色地带**：
结合 `missing_slots` 和对话上下文综合判断，可以谨慎进入执行，
但如有任何歧义则优先澄清。
```

---

## 四、整个流程的数据流

```
用户消息
    ↓
IntentDetectorMiddleware.abefore_agent()
    ↓ JointBERT 推理（线程池，不阻塞）
    ↓ 写入 state.intent
    ↓
MasterAgent MODEL 节点
    ↓ 读取 state.intent（confidence / missing_slots / main_intent）
    ↓
    ├─ confidence < 0.6      → 直接回复澄清问题，END
    ├─ main_intent = unknown → 回复兜底话术，END
    ├─ missing_slots 非空    → 追问 or 调工具补全
    └─ 一切正常              → 调用对应 SubAgent（researcher/analyst/...）
                                    ↓
                              SubAgent 内部也有 IntentDetectorMiddleware
                              （子任务的意图独立识别，不污染主 Agent 状态）
```

---

## 五、落地前的检查清单

| 检查项 | 标准 |
|---|---|
| 标注数据量 | 每个主意图 ≥ 500 条，unknown ≥ 200 条 |
| token 对齐 | `return_offsets_mapping=True`，slot loss 有 `ignore_index=-100` |
| 验证指标 | main_acc > 0.90，sub_acc > 0.85，slot_f1 > 0.80 才可上线 |
| 标签映射 | `label_config.json` 和模型权重一起保存，推理时从文件读 |
| 子意图掩码 | 推理时屏蔽非合法子意图，避免 `order_query` 预测出 `single_product` |
| 模型预加载 | 在 `lifespan` 里调用 `get_intent_service()`，不在第一次请求时加载 |
| 异步包装 | `abefore_agent` 用 `asyncio.to_thread`，不阻塞事件循环 |
| state_schema | `IntentDetectorMiddleware.state_schema = IntentDetectorState`，不能是 None |