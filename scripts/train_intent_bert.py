"""Train JointIntentSlotModel with early stopping, stratified splits, and per-class metrics."""

import json
import os
os.environ["HF_HUB_OFFLINE"] = "1"  # Must be set before any HF import
import random
import sys

import numpy as np
import torch
from torch.utils.data import DataLoader, TensorDataset
from transformers import BertTokenizer, get_linear_schedule_with_warmup
from seqeval.metrics import f1_score as seq_f1, classification_report as seq_report

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.services.joint_intent_model import JointIntentSlotModel
from src.agents.common.intent_schema import (
    MAIN_INTENTS, SUB_INTENTS, SLOT_TAGS, ID2SLOT_TAG,
    ID2MAIN_INTENT, ID2SUB_INTENT,
)
from scripts.prepare_joint_data import prepare_dataset_splits


# ══════════════════════════════════════════════════════════════════════
# Config
# ══════════════════════════════════════════════════════════════════════

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BERT_NAME = "hfl/chinese-roberta-wwm-ext"
DATA_FILE = os.path.join(PROJECT_ROOT, "scripts", "data", "joint_intent", "train.jsonl")
MODEL_DIR = os.path.join(PROJECT_ROOT, "models", "joint_intent_bert")
BATCH_SIZE = 16
GRADIENT_ACCUMULATION_STEPS = 2  # Effective batch size = 16 × 2 = 32
EPOCHS = 20
LR = 2e-5
WARMUP_RATIO = 0.1
WEIGHT_DECAY = 0.01
MAX_LEN = 128
SEED = 42
EARLY_STOPPING_PATIENCE = 5
LABEL_SMOOTHING = 0.1
SLOT_LOSS_WEIGHT = 2.0
SCHEDULED_SAMPLING_PROB = 0.3

# ══════════════════════════════════════════════════════════════════════
# Reproducibility
# ══════════════════════════════════════════════════════════════════════

random.seed(SEED)
np.random.seed(SEED)
torch.manual_seed(SEED)
if torch.cuda.is_available():
    torch.cuda.manual_seed_all(SEED)
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False

device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"[Device] {device}")

# ══════════════════════════════════════════════════════════════════════
# Data
# ══════════════════════════════════════════════════════════════════════

tokenizer = BertTokenizer.from_pretrained(BERT_NAME, local_files_only=True)

train_data, val_data, test_data, train_raw, val_raw, test_raw = \
    prepare_dataset_splits(DATA_FILE, tokenizer, MAX_LEN, augment=True, seed=SEED)

train_ds = TensorDataset(
    train_data["input_ids"], train_data["attention_mask"],
    train_data["main_intent_labels"], train_data["sub_intent_labels"],
    train_data["slot_labels"]
)
val_ds = TensorDataset(
    val_data["input_ids"], val_data["attention_mask"],
    val_data["main_intent_labels"], val_data["sub_intent_labels"],
    val_data["slot_labels"]
)
test_ds = TensorDataset(
    test_data["input_ids"], test_data["attention_mask"],
    test_data["main_intent_labels"], test_data["sub_intent_labels"],
    test_data["slot_labels"]
)

train_dl = DataLoader(train_ds, batch_size=BATCH_SIZE, shuffle=True)
val_dl = DataLoader(val_ds, batch_size=BATCH_SIZE * 2)
test_dl = DataLoader(test_ds, batch_size=BATCH_SIZE * 2)

print(f"[Data] train={len(train_raw)}, val={len(val_raw)}, test={len(test_raw)}")

# ══════════════════════════════════════════════════════════════════════
# Model
# ══════════════════════════════════════════════════════════════════════

model = JointIntentSlotModel(
    BERT_NAME,
    label_smoothing=LABEL_SMOOTHING,
    slot_loss_weight=SLOT_LOSS_WEIGHT,
    scheduled_sampling_prob=SCHEDULED_SAMPLING_PROB
).to(device)

optimizer = torch.optim.AdamW(model.parameters(), lr=LR, weight_decay=WEIGHT_DECAY)

total_steps = (len(train_dl) // GRADIENT_ACCUMULATION_STEPS) * EPOCHS
warmup_steps = int(total_steps * WARMUP_RATIO)
scheduler = get_linear_schedule_with_warmup(optimizer, warmup_steps, total_steps)

# ══════════════════════════════════════════════════════════════════════
# Evaluation
# ══════════════════════════════════════════════════════════════════════

def evaluate(model, loader, desc="Eval"):
    model.eval()
    main_correct = sub_correct = total = 0
    all_true_slots, all_pred_slots = [], []
    main_all_true, main_all_pred = [], []
    sub_all_true, sub_all_pred = [], []

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

            main_all_true.extend(main_lbl.cpu().tolist())
            main_all_pred.extend(main_pred.cpu().tolist())
            sub_all_true.extend(sub_lbl.cpu().tolist())
            sub_all_pred.extend(sub_pred.cpu().tolist())

            for true_seq, pred_seq in zip(slot_lbl.cpu().tolist(), slot_pred.cpu().tolist()):
                t = [ID2SLOT_TAG.get(l, "O") for l in true_seq if l != -100]
                p = [ID2SLOT_TAG.get(p, "O") for p, l in zip(pred_seq, true_seq) if l != -100]
                all_true_slots.append(t)
                all_pred_slots.append(p)

    from sklearn.metrics import f1_score as sk_f1, precision_score, recall_score

    slot_f1 = seq_f1(all_true_slots, all_pred_slots, zero_division=0)
    main_f1 = sk_f1(main_all_true, main_all_pred, average="macro", zero_division=0)
    sub_f1 = sk_f1(sub_all_true, sub_all_pred, average="macro", zero_division=0)

    return {
        "main_acc": main_correct / max(total, 1),
        "sub_acc": sub_correct / max(total, 1),
        "slot_f1": slot_f1,
        "main_f1": main_f1,
        "sub_f1": sub_f1,
    }


def final_eval(model, loader, raw_data, split_name="Test"):
    """Detailed evaluation with per-class metrics."""
    metrics = evaluate(model, loader)
    print(f"\n{'='*60}")
    print(f"[{split_name}] 最终评估")
    print(f"  Main Acc: {metrics['main_acc']:.4f} | Main F1: {metrics['main_f1']:.4f}")
    print(f"  Sub  Acc: {metrics['sub_acc']:.4f} | Sub  F1: {metrics['sub_f1']:.4f}")
    print(f"  Slot F1 : {metrics['slot_f1']:.4f}")

    # Per-class main intent accuracy
    from collections import defaultdict
    per_class = defaultdict(lambda: {"correct": 0, "total": 0})
    model.eval()
    with torch.no_grad():
        for batch, raw_items in zip(loader, [raw_data[i:i+BATCH_SIZE*2] for i in range(0, len(raw_data), BATCH_SIZE*2)]):
            if not raw_items:
                continue
            ids, mask, main_lbl, sub_lbl, slot_lbl = [b.to(device) for b in batch]
            out = model(input_ids=ids, attention_mask=mask)
            main_pred = out["main_intent_logits"].argmax(-1)
            for pred, true in zip(main_pred.cpu().tolist(), main_lbl.cpu().tolist()):
                cls_name = ID2MAIN_INTENT.get(true, str(true))
                per_class[cls_name]["total"] += 1
                if pred == true:
                    per_class[cls_name]["correct"] += 1

    print(f"\n  主意图每类准确率:")
    for cls_name in MAIN_INTENTS:
        stats = per_class.get(cls_name, {"correct": 0, "total": 0})
        if stats["total"] > 0:
            acc = stats["correct"] / stats["total"]
            print(f"    {cls_name:25s}: {stats['total']:4d} 条, acc={acc:.3f}")
        else:
            print(f"    {cls_name:25s}:     0 条")

    return metrics


# ══════════════════════════════════════════════════════════════════════
# Training loop
# ══════════════════════════════════════════════════════════════════════

best_slot_f1 = 0.0
best_epoch = 0
no_improve = 0

for epoch in range(EPOCHS):
    model.train()
    total_loss = 0.0
    optimizer.zero_grad()

    for step, batch in enumerate(train_dl):
        ids, mask, main_lbl, sub_lbl, slot_lbl = [b.to(device) for b in batch]
        out = model(ids, mask, main_lbl, sub_lbl, slot_lbl)
        loss = out["loss"] / GRADIENT_ACCUMULATION_STEPS
        loss.backward()
        total_loss += loss.item()

        if (step + 1) % GRADIENT_ACCUMULATION_STEPS == 0:
            torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            optimizer.step()
            scheduler.step()
            optimizer.zero_grad()

    # Evaluate
    metrics = evaluate(model, val_dl)
    print(
        f"Epoch {epoch + 1:2d}/{EPOCHS} | "
        f"loss={total_loss:.3f} | "
        f"main_acc={metrics['main_acc']:.3f} main_f1={metrics['main_f1']:.3f} | "
        f"sub_acc={metrics['sub_acc']:.3f} sub_f1={metrics['sub_f1']:.3f} | "
        f"slot_f1={metrics['slot_f1']:.3f}"
    )

    # Early stopping on slot_f1
    if metrics["slot_f1"] > best_slot_f1 + 0.001:
        best_slot_f1 = metrics["slot_f1"]
        best_epoch = epoch + 1
        no_improve = 0
        os.makedirs(MODEL_DIR, exist_ok=True)
        torch.save(model.state_dict(), f"{MODEL_DIR}/model.pth")
        tokenizer.save_pretrained(MODEL_DIR)
        model.bert.save_pretrained(MODEL_DIR)
        json.dump(
            {"main_intents": MAIN_INTENTS, "sub_intents": SUB_INTENTS},
            open(f"{MODEL_DIR}/label_config.json", "w", encoding="utf-8"),
            ensure_ascii=False, indent=2
        )
        print(f"  → 保存最优模型 (slot_f1={best_slot_f1:.3f})")
    else:
        no_improve += 1
        if no_improve >= EARLY_STOPPING_PATIENCE:
            print(f"\nEarly stopping: slot_f1 {EARLY_STOPPING_PATIENCE} 轮未提升")
            break

print(f"\n训练完成，最优模型: epoch={best_epoch}, slot_f1={best_slot_f1:.3f}")

# ══════════════════════════════════════════════════════════════════════
# Final test evaluation
# ══════════════════════════════════════════════════════════════════════

model_path = os.path.join(MODEL_DIR, "model.pth")
if os.path.exists(model_path) and best_epoch > 0:
    model.load_state_dict(torch.load(model_path, map_location=device))
    final_eval(model, test_dl, test_raw, "Test")
else:
    print(f"\nNo valid checkpoint saved (best_epoch={best_epoch}), skipping test evaluation")
