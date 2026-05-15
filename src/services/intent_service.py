import json
import torch
from pathlib import Path
from transformers import BertTokenizer
from src.services.joint_intent_model import JointIntentSlotModel


class JointIntentService:
    """单例意图识别服务，应用启动时初始化"""

    def __init__(self, model_dir: str = None):
        if model_dir is None:
            # 使用项目根目录的绝对路径
            project_root = Path(__file__).parent.parent.parent
            model_dir = str(project_root / "models" / "joint_intent_bert")
        cfg = json.load(open(f"{model_dir}/label_config.json", encoding="utf-8"))
        self._main_intents = cfg["main_intents"]
        self._sub_intents = cfg["sub_intents"]

        self._tokenizer = BertTokenizer.from_pretrained(model_dir)
        self._model = JointIntentSlotModel(bert_model_name=model_dir)
        self._model.load_state_dict(
            torch.load(f"{model_dir}/model.pth", map_location="cpu")
        )
        self._model.eval()
        self._device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self._model.to(self._device)

    def predict(self, text: str, confidence_threshold: float = 0.6) -> dict:
        """同步推理接口"""
        # 延迟导入，避免循环依赖
        from src.agents.common.intent_schema import (
            VALID_SUB_INTENTS, get_required_slots,
            ID2MAIN_INTENT, ID2SUB_INTENT, ID2SLOT_TAG
        )
        
        enc = self._tokenizer(
            text, return_tensors="pt",
            truncation=True, max_length=128,
            return_offsets_mapping=True
        )
        offsets = enc.pop("offset_mapping")
        # 只保留模型需要的参数
        enc = {k: v.to(self._device) for k, v in enc.items() if k in ["input_ids", "attention_mask"]}

        with torch.no_grad():
            out = self._model(**enc)

        # 主意图
        main_probs = torch.softmax(out["main_intent_logits"], dim=-1)[0].cpu()
        main_idx = main_probs.argmax().item()
        main_conf = main_probs[main_idx].item()
        main_intent = self._main_intents[main_idx]

        # 子意图（只在合法子意图里取最大值）
        sub_probs = torch.softmax(out["sub_intent_logits"], dim=-1)[0].cpu()
        valid_subs = VALID_SUB_INTENTS.get(main_intent, {"none"})
        for i, name in enumerate(self._sub_intents):
            if name not in valid_subs:
                sub_probs[i] = -1e9
        sub_idx = sub_probs.argmax().item()
        sub_intent = self._sub_intents[sub_idx]
        if sub_intent == "none":
            sub_intent = None

        # 槽位（BIO 解码，对齐回原始字符）
        slot_preds = out["slot_logits"][0].argmax(-1).cpu().tolist()
        slots = self._decode_slots(text, slot_preds, offsets[0].tolist(), ID2SLOT_TAG)

        # 缺失槽位
        required = get_required_slots(main_intent, sub_intent)
        missing_slots = [s for s in required if s not in slots]

        return {
            "raw_input": text,
            "main_intent": main_intent,
            "sub_intent": sub_intent,
            "slots": slots,
            "missing_slots": missing_slots,
            "intent_confidence": round(main_conf, 4),
            "clarification_needed": main_conf < confidence_threshold
        }

    def _decode_slots(self, text: str, token_preds: list, offsets: list, ID2SLOT_TAG: dict) -> dict:
        """从 BIO 标签解码槽位"""
        slots = {}
        current_entity, current_chars = None, []

        for pred_id, (char_s, char_e) in zip(token_preds, offsets):
            if char_s == char_e:  # 特殊 token，跳过
                continue
            tag = ID2SLOT_TAG.get(pred_id, "O")

            if tag.startswith("B-"):
                if current_entity:
                    slots[current_entity] = "".join(current_chars)
                current_entity = tag[2:]
                current_chars = [text[char_s:char_e]]

            elif tag.startswith("I-") and current_entity == tag[2:]:
                current_chars.append(text[char_s:char_e])

            else:
                if current_entity:
                    slots[current_entity] = "".join(current_chars)
                    current_entity, current_chars = None, []

        if current_entity:
            slots[current_entity] = "".join(current_chars)

        return slots


# 全局单例
_intent_service: JointIntentService | None = None


def get_intent_service() -> JointIntentService:
    """获取单例服务（懒加载）"""
    global _intent_service
    if _intent_service is None:
        _intent_service = JointIntentService()
    return _intent_service
