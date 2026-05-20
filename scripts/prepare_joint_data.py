"""Prepare JointBERT training data with cleaning, stratified split, and augmentation."""

import json
import random
import sys
import os
from collections import Counter

import torch
from transformers import BertTokenizer

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.agents.common.intent_schema import (
    MAIN_INTENTS, SUB_INTENTS, SLOT_TAGS,
    MAIN_INTENT2ID, SUB_INTENT2ID, SLOT_TAG2ID,
    VALID_SUB_INTENTS,
)

ID2SLOT_TAG = {i: v for v, i in SLOT_TAG2ID.items()}
ID2MAIN_INTENT = {i: v for v, i in MAIN_INTENT2ID.items()}
ID2SUB_INTENT = {i: v for v, i in SUB_INTENT2ID.items()}


# ══════════════════════════════════════════════════════════════════════
# 1. Data loading & cleaning
# ══════════════════════════════════════════════════════════════════════

def load_and_clean(file_path: str) -> list[dict]:
    """Load JSONL, deduplicate by text, validate labels and slot boundaries."""
    with open(file_path, encoding="utf-8") as f:
        raw = [json.loads(line.strip()) for line in f if line.strip()]

    # --- Dedup by text (keep first) ---
    seen = set()
    deduped = []
    for item in raw:
        key = item["text"]
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    dup_count = len(raw) - len(deduped)
    if dup_count:
        print(f"[Clean] 去重: {dup_count} 条 ({len(raw)} → {len(deduped)})")

    # --- Validate & fix ---
    clean = []
    skipped = 0
    for item in deduped:
        text = item.get("text", "")
        main = item.get("main_intent", "")
        sub = item.get("sub_intent", "none")
        slots = item.get("slots", [])

        # Validate intent labels
        if main not in MAIN_INTENT2ID:
            skipped += 1
            continue
        if sub not in SUB_INTENT2ID:
            sub = "none"

        # Validate sub-intent consistency
        valid_subs = VALID_SUB_INTENTS.get(main, {"none"})
        if sub not in valid_subs:
            # Auto-correct: map to first valid sub or "none"
            sub = next(iter(valid_subs)) if valid_subs else "none"

        # Validate & auto-correct slots
        valid_slots = []
        for s in slots:
            entity = s.get("entity", "")
            if f"B-{entity}" not in SLOT_TAG2ID:
                continue

            start, end = s.get("start", 0), s.get("end", 0)
            value = s.get("value", "")

            if not (0 <= start < end <= len(text)):
                continue

            if text[start:end] != value:
                # Try to auto-correct position
                real_start = text.find(value, max(0, start - 3))
                if real_start != -1:
                    start, end = real_start, real_start + len(value)
                else:
                    continue

            valid_slots.append({
                "entity": entity,
                "start": start,
                "end": end,
                "value": value
            })

        # Sort slots by position
        valid_slots.sort(key=lambda x: (x["start"], x["end"]))

        # Remove overlapping slots (keep first)
        non_overlap = []
        for s in valid_slots:
            if not any(
                not (s["end"] <= ns["start"] or s["start"] >= ns["end"])
                for ns in non_overlap
            ):
                non_overlap.append(s)

        clean.append({
            "text": text,
            "main_intent": main,
            "sub_intent": sub,
            "slots": non_overlap
        })

    if skipped:
        print(f"[Clean] 跳过 {skipped} 条无效样本")

    return clean


# ══════════════════════════════════════════════════════════════════════
# 2. Data augmentation (lightweight, text-level)
# ══════════════════════════════════════════════════════════════════════

SYNONYM_MAP = {
    "想买": ["想入手", "想买个", "帮我推荐", "帮我找", "推荐一款"],
    "帮我": ["帮忙", "帮我"],
    "有没有": ["有没", "有没有"],
    "推荐": ["介绍", "安利", "推荐"],
    "哪个好": ["哪个更好", "选哪个", "哪个值得买", "哪个好"],
    "怎么样": ["怎么样", "如何", "行不行", "好不好"],
    "多少钱": ["什么价", "多少钱", "价格多少"],
    "便宜": ["实惠", "划算", "便宜", "性价比高"],
    "质量": ["做工", "质量", "品质"],
}

def augment_text(text: str, slots: list[dict], max_augments: int = 2) -> list[tuple[str, list[dict]]]:
    """Generate lightweight augmented variants by synonym replacement.

    Only replaces words outside entity spans so slot positions stay valid.
    Returns list of (augmented_text, adjusted_slots).
    """
    variants = []

    # Build mask: chars inside slots are protected
    protected = [False] * len(text)
    for s in slots:
        for i in range(s["start"], s["end"]):
            protected[i] = True

    for old_word, replacements in SYNONYM_MAP.items():
        if len(variants) >= max_augments:
            break

        # Find all occurrences outside protected regions
        idx = 0
        while True:
            idx = text.find(old_word, idx)
            if idx == -1:
                break
            end = idx + len(old_word)

            # Check if overlap with protected region
            if not any(protected[idx:end]):
                for rep in replacements[:1]:  # Only use first replacement
                    if rep == old_word:
                        continue
                    new_text = text[:idx] + rep + text[end:]
                    # Adjust slot positions after the replacement
                    delta = len(rep) - len(old_word)
                    new_slots = []
                    for s in slots:
                        ns = dict(s)
                        if s["start"] >= end:
                            ns["start"] += delta
                            ns["end"] += delta
                        new_slots.append(ns)
                    variants.append((new_text, new_slots))
                    break

            idx = end

    return variants


# ══════════════════════════════════════════════════════════════════════
# 3. Stratified split
# ══════════════════════════════════════════════════════════════════════

def stratified_split(data: list[dict], val_ratio: float = 0.15, test_ratio: float = 0.10,
                     seed: int = 42) -> tuple[list, list, list]:
    """Split data stratified by main_intent with fixed seed for reproducibility."""
    random.seed(seed)

    # Group by main_intent
    groups: dict[str, list] = {}
    for item in data:
        groups.setdefault(item["main_intent"], []).append(item)

    train, val, test = [], [], []

    for intent, items in groups.items():
        random.shuffle(items)
        n = len(items)
        n_test = max(1, int(n * test_ratio))
        n_val = max(1, int(n * val_ratio))
        n_train = n - n_val - n_test

        if n_train < 1:
            # Too few samples, put all in train
            train.extend(items)
        else:
            train.extend(items[:n_train])
            val.extend(items[n_train:n_train + n_val])
            test.extend(items[n_train + n_val:])

    random.shuffle(train)
    random.shuffle(val)
    random.shuffle(test)

    return train, val, test


# ══════════════════════════════════════════════════════════════════════
# 4. Token-level encoding
# ══════════════════════════════════════════════════════════════════════

def build_token_labels(text: str, char_slots: list, tokenizer) -> list[int]:
    """Map char-level slot annotations to token-level BIO tags."""
    encoding = tokenizer(text, return_offsets_mapping=True, add_special_tokens=True)
    offsets = encoding["offset_mapping"]

    char_labels = ["O"] * len(text)
    for slot in char_slots:
        entity = slot["entity"]
        s, e = slot["start"], slot["end"]
        if s < len(char_labels):
            char_labels[s] = f"B-{entity}"
        for i in range(s + 1, min(e, len(char_labels))):
            char_labels[i] = f"I-{entity}"

    token_labels = []
    for char_start, char_end in offsets:
        if char_start == char_end:
            token_labels.append(-100)  # Special tokens ignored
        else:
            token_labels.append(SLOT_TAG2ID.get(char_labels[char_start], 0))

    return token_labels


def prepare_dataset(file_path: str, tokenizer, max_len: int = 128,
                    augment: bool = False) -> dict:
    """Load, clean, optionally augment, and encode data as tensors."""
    data = load_and_clean(file_path)

    if augment:
        aug_count = 0
        augmented = []
        for item in data:
            augmented.append(item)
            variants = augment_text(item["text"], item["slots"], max_augments=1)
            for new_text, new_slots in variants:
                augmented.append({
                    "text": new_text,
                    "main_intent": item["main_intent"],
                    "sub_intent": item["sub_intent"],
                    "slots": new_slots
                })
                aug_count += 1
        print(f"[Augment] 新增 {aug_count} 条增强样本")
        data = augmented

    input_ids_list, attention_masks_list = [], []
    main_labels, sub_labels, slot_labels_list = [], [], []

    for item in data:
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


def prepare_dataset_splits(file_path: str, tokenizer, max_len: int = 128,
                           augment: bool = False, seed: int = 42):
    """Load data, do stratified split, encode each split separately.

    Returns (train_data, val_data, test_data) dicts and the raw splits.
    """
    raw_data = load_and_clean(file_path)

    # Print distribution
    print(f"\n[Data] 清洗后总计: {len(raw_data)} 条")
    main_dist = Counter(d["main_intent"] for d in raw_data)
    for intent, cnt in sorted(main_dist.items()):
        print(f"  {intent}: {cnt}")

    train_raw, val_raw, test_raw = stratified_split(raw_data, seed=seed)
    print(f"[Split] train={len(train_raw)}, val={len(val_raw)}, test={len(test_raw)}")

    # Augment only training set
    if augment:
        aug_count = 0
        augmented = []
        for item in train_raw:
            augmented.append(item)
            variants = augment_text(item["text"], item["slots"], max_augments=1)
            for new_text, new_slots in variants:
                augmented.append({
                    "text": new_text,
                    "main_intent": item["main_intent"],
                    "sub_intent": item["sub_intent"],
                    "slots": new_slots
                })
                aug_count += 1
        print(f"[Augment] 训练集新增 {aug_count} 条增强样本")
        train_raw = augmented

    def encode(data_list):
        return prepare_dataset_from_list(data_list, tokenizer, max_len)

    return encode(train_raw), encode(val_raw), encode(test_raw), train_raw, val_raw, test_raw


def prepare_dataset_from_list(data: list[dict], tokenizer, max_len: int = 128) -> dict:
    """Encode a list of samples into tensor dict."""
    input_ids_list, attention_masks_list = [], []
    main_labels, sub_labels, slot_labels_list = [], [], []

    for item in data:
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
