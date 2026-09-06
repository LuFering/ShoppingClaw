"""
独立训练脚本 - 不依赖主项目模块
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset, random_split
from transformers import BertTokenizer, BertModel, get_linear_schedule_with_warmup
from seqeval.metrics import f1_score as seq_f1
import json

# ==================== 配置常量 ====================
MAIN_INTENTS = ["product_recommend", "product_comparison", "order_query", "after_sales", "price_check", "store_search", "unknown"]
SUB_INTENTS = [
    "single_product", "multi_compare",
    "direct_compare", "category_compare",
    "status_check", "logistics_track",
    "return_request", "repair_request",
    "none"
]
SLOT_TAGS = [
    "O",
    "B-category", "I-category",
    "B-brand", "I-brand",
    "B-budget_max", "I-budget_max",
    "B-budget_min", "I-budget_min",
    "B-product_a", "I-product_a",
    "B-product_b", "I-product_b",
    "B-order_id", "I-order_id",
    "B-reason", "I-reason",
    "B-issue_type", "I-issue_type",
]

MAIN_INTENT2ID = {v: i for i, v in enumerate(MAIN_INTENTS)}
SUB_INTENT2ID = {v: i for i, v in enumerate(SUB_INTENTS)}
SLOT_TAG2ID = {v: i for i, v in enumerate(SLOT_TAGS)}
ID2SLOT_TAG = {i: v for i, v in enumerate(SLOT_TAGS)}

# ==================== 模型定义 ====================
class JointIntentSlotModel(nn.Module):
    def __init__(self, bert_model_name: str = "hfl/chinese-roberta-wwm-ext"):
        super().__init__()
        self.bert = BertModel.from_pretrained(bert_model_name)
        hidden = self.bert.config.hidden_size

        n_main = len(MAIN_INTENTS)
        n_sub = len(SUB_INTENTS)
        n_slot = len(SLOT_TAGS)

        self.main_clf = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden, n_main)
        )

        self.sub_clf = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden + n_main, hidden // 2),
            nn.GELU(),
            nn.Linear(hidden // 2, n_sub)
        )

        self.slot_clf = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden, n_slot)
        )

    def forward(self, input_ids, attention_mask, main_intent_labels=None, sub_intent_labels=None, slot_labels=None):
        out = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        seq_out = out.last_hidden_state
        cls_out = out.pooler_output

        main_logits = self.main_clf(cls_out)

        if main_intent_labels is not None:
            main_onehot = torch.zeros_like(main_logits).scatter_(1, main_intent_labels.unsqueeze(1), 1.0)
        else:
            main_onehot = torch.softmax(main_logits, dim=-1).detach()

        sub_logits = self.sub_clf(torch.cat([cls_out, main_onehot], dim=-1))
        slot_logits = self.slot_clf(seq_out)

        result = {
            "main_intent_logits": main_logits,
            "sub_intent_logits": sub_logits,
            "slot_logits": slot_logits
        }

        if main_intent_labels is not None:
            loss_main = nn.CrossEntropyLoss()(main_logits, main_intent_labels)
            loss_sub = nn.CrossEntropyLoss()(sub_logits, sub_intent_labels)
            loss_slot = nn.CrossEntropyLoss(ignore_index=-100)(
                slot_logits.view(-1, slot_logits.size(-1)),
                slot_labels.view(-1)
            )
            result["loss"] = loss_main + loss_sub + loss_slot

        return result

# ==================== 数据处理 ====================
def build_token_labels(text, char_slots, tokenizer):
    encoding = tokenizer(text, return_offsets_mapping=True, add_special_tokens=True)
    offsets = encoding["offset_mapping"]

    char_labels = ["O"] * len(text)
    for slot in char_slots:
        entity = slot["entity"]
        s, e = slot["start"], slot["end"]
        char_labels[s] = f"B-{entity}"
        for i in range(s + 1, e):
            char_labels[i] = f"I-{entity}"

    token_labels = []
    for char_start, char_end in offsets:
        if char_start == char_end:
            token_labels.append(-100)
        else:
            token_labels.append(SLOT_TAG2ID.get(char_labels[char_start], 0))

    return token_labels


def prepare_dataset(file_path, tokenizer, max_len=128):
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
                return_offsets_mapping=True
            )

            token_slot_labels = build_token_labels(text, item["slots"], tokenizer)
            pad_len = max_len - len(token_slot_labels)
            token_slot_labels = token_slot_labels[:max_len] + [-100] * pad_len

            input_ids_list.append(torch.tensor(encoding["input_ids"]))
            attention_masks_list.append(torch.tensor(encoding["attention_mask"]))
            main_labels.append(MAIN_INTENT2ID[item["main_intent"]])
            sub_labels.append(SUB_INTENT2ID[item["sub_intent"]])
            slot_labels_list.append(torch.tensor(token_slot_labels))

    return {
        "input_ids": torch.stack(input_ids_list),
        "attention_mask": torch.stack(attention_masks_list),
        "main_intent_labels": torch.tensor(main_labels),
        "sub_intent_labels": torch.tensor(sub_labels),
        "slot_labels": torch.stack(slot_labels_list)
    }

# ==================== 评估函数 ====================
def evaluate(model, loader, device):
    model.eval()
    main_correct = sub_correct = total = 0
    all_true_slots, all_pred_slots = [], []

    with torch.no_grad():
        for batch in loader:
            ids, mask, main_lbl, sub_lbl, slot_lbl = [b.to(device) for b in batch]
            out = model(input_ids=ids, attention_mask=mask)

            main_pred = out["main_intent_logits"].argmax(-1)
            sub_pred = out["sub_intent_logits"].argmax(-1)
            slot_pred = out["slot_logits"].argmax(-1)

            main_correct += (main_pred == main_lbl).sum().item()
            sub_correct += (sub_pred == sub_lbl).sum().item()
            total += main_lbl.size(0)

            for true_seq, pred_seq in zip(slot_lbl.cpu().tolist(), slot_pred.cpu().tolist()):
                t = [ID2SLOT_TAG.get(l, "O") for l in true_seq if l != -100]
                p = [ID2SLOT_TAG.get(p, "O") for p, l in zip(pred_seq, true_seq) if l != -100]
                all_true_slots.append(t)
                all_pred_slots.append(p)

    slot_f1 = seq_f1(all_true_slots, all_pred_slots, zero_division=0)
    return {
        "main_acc": main_correct / total,
        "sub_acc": sub_correct / total,
        "slot_f1": slot_f1
    }

# ==================== 主训练流程 ====================
if __name__ == "__main__":
    # 配置
    BERT_NAME = "hfl/chinese-roberta-wwm-ext"
    DATA_FILE = "scripts/data/joint_intent/train.jsonl"
    MODEL_DIR = "./model/joint_intent_bert"
    BATCH_SIZE = 16
    EPOCHS = 5
    LR = 2e-5
    MAX_LEN = 128

    print("加载tokenizer...")
    tokenizer = BertTokenizer.from_pretrained(BERT_NAME)
    
    print("准备数据集...")
    data = prepare_dataset(DATA_FILE, tokenizer, MAX_LEN)

    dataset = TensorDataset(
        data["input_ids"], data["attention_mask"],
        data["main_intent_labels"], data["sub_intent_labels"],
        data["slot_labels"]
    )
    val_size = max(int(len(dataset) * 0.15), 1)
    train_ds, val_ds = random_split(dataset, [len(dataset) - val_size, val_size])

    train_dl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
    val_dl = DataLoader(val_ds, batch_size=32)

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"使用设备: {device}")
    
    print("初始化模型...")
    model = JointIntentSlotModel(BERT_NAME).to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=0.01)
    total_steps = len(train_dl) * EPOCHS
    scheduler = get_linear_schedule_with_warmup(
        optimizer,
        num_warmup_steps=total_steps // 10,
        num_training_steps=total_steps
    )

    best_slot_f1 = 0.0
    for epoch in range(EPOCHS):
        model.train()
        for batch_idx, batch in enumerate(train_dl):
            ids, mask, main_lbl, sub_lbl, slot_lbl = [b.to(device) for b in batch]
            out = model(ids, mask, main_lbl, sub_lbl, slot_lbl)
            loss = out["loss"]
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

            if (batch_idx + 1) % 5 == 0:
                print(f"  Epoch {epoch+1} | Batch {batch_idx+1}/{len(train_dl)} | Loss: {loss.item():.4f}")

        metrics = evaluate(model, val_dl, device)
        print(f"\nEpoch {epoch+1} 完成:")
        print(f"  主意图准确率: {metrics['main_acc']:.3f}")
        print(f"  子意图准确率: {metrics['sub_acc']:.3f}")
        print(f"  槽位F1分数:   {metrics['slot_f1']:.3f}\n")

        if metrics["slot_f1"] > best_slot_f1:
            best_slot_f1 = metrics["slot_f1"]
            os.makedirs(MODEL_DIR, exist_ok=True)
            torch.save(model.state_dict(), f"{MODEL_DIR}/model.pth")
            tokenizer.save_pretrained(MODEL_DIR)
            json.dump({
                "main_intents": MAIN_INTENTS,
                "sub_intents": SUB_INTENTS,
                "slot_tags": SLOT_TAGS
            }, open(f"{MODEL_DIR}/label_config.json", "w", encoding="utf-8"),
            ensure_ascii=False, indent=2)
            print(f"  ✅ 保存最优模型 (slot_f1={best_slot_f1:.3f})\n")

    print("="*60)
    print("训练完成！")
    print(f"最优槽位F1: {best_slot_f1:.3f}")
    print(f"模型保存路径: {MODEL_DIR}")
    print("="*60)
