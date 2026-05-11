import torch
import torch.nn as nn
from transformers import BertModel

# 延迟导入，避免循环依赖
def _get_schema():
    from src.agents.common.intent_schema import MAIN_INTENTS, SUB_INTENTS, SLOT_TAGS
    return MAIN_INTENTS, SUB_INTENTS, SLOT_TAGS


class JointIntentSlotModel(nn.Module):
    """JointBERT：意图分类 + 槽位填充联合模型"""

    def __init__(self, bert_model_name: str = "C:\\Users\\25153\\.cache\\huggingface\\hub\\models--hfl--chinese-roberta-wwm-ext\\snapshots\\5c58d0b8ec1d9014354d691c538661bf00bfdb44"):
        super().__init__()
        # 使用本地缓存的BERT模型，避免联网下载
        self.bert = BertModel.from_pretrained(bert_model_name)
        hidden = self.bert.config.hidden_size  # 768

        MAIN_INTENTS, SUB_INTENTS, SLOT_TAGS = _get_schema()
        n_main = len(MAIN_INTENTS)
        n_sub = len(SUB_INTENTS)
        n_slot = len(SLOT_TAGS)

        # 主意图头
        self.main_clf = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden, n_main)
        )

        # 子意图头：拼接 [CLS] 向量 + 主意图 softmax 概率
        self.sub_clf = nn.Sequential(
            nn.Dropout(0.1),
            nn.Linear(hidden + n_main, hidden // 2),
            nn.GELU(),
            nn.Linear(hidden // 2, n_sub)
        )

        # 槽位序列标注头
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
        seq_out = out.last_hidden_state  # [B, L, H]
        cls_out = out.pooler_output  # [B, H]

        # 主意图
        main_logits = self.main_clf(cls_out)  # [B, n_main]

        # 子意图：用真实主意图（训练）或预测概率（推理）拼接
        if main_intent_labels is not None:
            main_onehot = torch.zeros_like(main_logits).scatter_(
                1, main_intent_labels.unsqueeze(1), 1.0
            )
        else:
            main_onehot = torch.softmax(main_logits, dim=-1).detach()

        sub_logits = self.sub_clf(
            torch.cat([cls_out, main_onehot], dim=-1)
        )  # [B, n_sub]

        # 槽位
        slot_logits = self.slot_clf(seq_out)  # [B, L, n_slot]

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
