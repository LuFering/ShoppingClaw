import random

import torch
import torch.nn as nn
from transformers import BertModel, BertConfig

# Disable the background safetensors auto-conversion thread that tries to
# reach huggingface.co even when local_files_only=True (crashes on mainland
# China networks with ConnectError).
from transformers import safetensors_conversion as _sc
_sc.auto_conversion = lambda *a, **kw: None


def _get_schema():
    from src.agents.common.intent_schema import MAIN_INTENTS, SUB_INTENTS, SLOT_TAGS
    return MAIN_INTENTS, SUB_INTENTS, SLOT_TAGS


class JointIntentSlotModel(nn.Module):
    """JointBERT: intent classification + slot filling with scheduled sampling."""

    def __init__(self, bert_model_name: str | None = None,
                 label_smoothing: float = 0.1,
                 slot_loss_weight: float = 2.0,
                 scheduled_sampling_prob: float = 0.3):
        super().__init__()
        self.label_smoothing = label_smoothing
        self.slot_loss_weight = slot_loss_weight
        self.scheduled_sampling_prob = scheduled_sampling_prob

        if bert_model_name is None:
            bert_model_name = "hfl/chinese-roberta-wwm-ext"
        self.bert = BertModel.from_pretrained(bert_model_name, local_files_only=True)

        hidden = self.bert.config.hidden_size  # 768
        MAIN_INTENTS, SUB_INTENTS, SLOT_TAGS = _get_schema()
        n_main = len(MAIN_INTENTS)
        n_sub = len(SUB_INTENTS)
        n_slot = len(SLOT_TAGS)

        self.main_clf = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden, n_main)
        )

        # Sub-intent head: [CLS] + main intent probabilities
        self.sub_clf = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden + n_main, hidden // 2),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(hidden // 2, n_sub)
        )

        # Slot sequence labeling head
        self.slot_clf = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden, n_slot)
        )

    def forward(
            self,
            input_ids: torch.Tensor,
            attention_mask: torch.Tensor,
            main_intent_labels: torch.Tensor | None = None,
            sub_intent_labels: torch.Tensor | None = None,
            slot_labels: torch.Tensor | None = None
    ) -> dict:
        out = self.bert(input_ids=input_ids, attention_mask=attention_mask)
        seq_out = out.last_hidden_state   # [B, L, H]
        cls_out = out.pooler_output       # [B, H]

        main_logits = self.main_clf(cls_out)  # [B, n_main]

        # Sub-intent: scheduled sampling to reduce exposure bias
        # During training, use predicted main intent with probability `scheduled_sampling_prob`
        if main_intent_labels is not None and self.training:
            use_predicted = random.random() < self.scheduled_sampling_prob
            if use_predicted:
                main_onehot = torch.softmax(main_logits, dim=-1).detach()
            else:
                main_onehot = torch.zeros_like(main_logits).scatter_(
                    1, main_intent_labels.unsqueeze(1), 1.0
                )
        elif main_intent_labels is not None:
            main_onehot = torch.zeros_like(main_logits).scatter_(
                1, main_intent_labels.unsqueeze(1), 1.0
            )
        else:
            main_onehot = torch.softmax(main_logits, dim=-1).detach()

        sub_logits = self.sub_clf(
            torch.cat([cls_out, main_onehot], dim=-1)
        )  # [B, n_sub]

        slot_logits = self.slot_clf(seq_out)  # [B, L, n_slot]

        result = {
            "main_intent_logits": main_logits,
            "sub_intent_logits": sub_logits,
            "slot_logits": slot_logits
        }

        if main_intent_labels is not None:
            loss_main = nn.CrossEntropyLoss(
                label_smoothing=self.label_smoothing
            )(main_logits, main_intent_labels)
            loss_sub = nn.CrossEntropyLoss(
                label_smoothing=self.label_smoothing
            )(sub_logits, sub_intent_labels)
            loss_slot = nn.CrossEntropyLoss(ignore_index=-100)(
                slot_logits.view(-1, slot_logits.size(-1)),
                slot_labels.view(-1)
            )
            result["loss"] = loss_main + loss_sub + self.slot_loss_weight * loss_slot

        return result
