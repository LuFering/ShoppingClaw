"""
意图体系唯一数据源
训练脚本、推理服务、Middleware 全部 import 这里
"""

# ==================== 意图树状结构定义 ====================

INTENT_SCHEMA = {
    "product_recommend": {
        "required": ["category"],  # 默认必填槽位
        "sub_intents": {
            "single_product": {
                "required": ["category"],
                "optional": ["budget_max", "brand", "usage_scenario"]
            },
            "multi_compare": {
                "required": ["category"],
                "optional": ["budget_min", "budget_max", "brands"]
            }
        }
    },
    "product_comparison": {
        "sub_intents": {
            "direct_compare": {
                "required": ["product_a", "product_b"],
                "optional": ["dimensions"]
            },
            "category_compare": {
                "required": ["category"],
                "optional": ["budget_range", "brands"]
            }
        }
    },
    "order_query": {
        "sub_intents": {
            "status_check": {
                "required": ["order_id"],
                "optional": ["phone_number"]
            },
            "logistics_track": {
                "required": ["order_id"],
                "optional": []
            }
        }
    },
    "after_sales": {
        "sub_intents": {
            "return_request": {
                "required": ["order_id", "reason"],
                "optional": []
            },
            "repair_request": {
                "required": ["order_id", "issue_type"],
                "optional": []
            }
        }
    },
    "price_check": {
        "sub_intents": None,
        "required": ["category"],
        "optional": ["brand"]
    },
    "store_search": {
        "sub_intents": None,
        "required": ["brand"],
        "optional": ["category"]
    },
    "greeting": {
        "sub_intents": None,
        "required": [],
        "optional": []
    },
    "unknown": {
        "sub_intents": None,
        "required": [],
        "optional": []
    }
}

# ==================== 标签枚举（顺序固定，不可修改）====================

MAIN_INTENTS = list(INTENT_SCHEMA.keys())
# ['product_recommend', 'product_comparison', 'order_query',
#  'after_sales', 'price_check', 'store_search', 'greeting', 'unknown']

SUB_INTENTS = [
    "single_product", "multi_compare",
    "direct_compare", "category_compare",
    "status_check", "logistics_track",
    "return_request", "repair_request",
    "none"  # 代表无子意图
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

# ==================== ID 映射表 ====================

MAIN_INTENT2ID = {v: i for i, v in enumerate(MAIN_INTENTS)}
SUB_INTENT2ID = {v: i for i, v in enumerate(SUB_INTENTS)}
SLOT_TAG2ID = {v: i for i, v in enumerate(SLOT_TAGS)}

ID2MAIN_INTENT = {i: v for v, i in MAIN_INTENT2ID.items()}
ID2SUB_INTENT = {i: v for v, i in SUB_INTENT2ID.items()}
ID2SLOT_TAG = {i: v for v, i in SLOT_TAG2ID.items()}

# ==================== 约束规则 ====================

# 主意图 → 合法子意图集合（推理时掩码用）
VALID_SUB_INTENTS = {
    "product_recommend": {"single_product", "multi_compare"},
    "product_comparison": {"direct_compare", "category_compare"},
    "order_query": {"status_check", "logistics_track"},
    "after_sales": {"return_request", "repair_request"},
    "price_check": {"none"},
    "store_search": {"none"},
    "greeting": {"none"},
    "unknown": {"none"}
}


def get_required_slots(main_intent: str, sub_intent: str | None) -> list[str]:
    """获取必填槽位列表"""
    schema = INTENT_SCHEMA.get(main_intent, {})
    if schema.get("sub_intents") and sub_intent and sub_intent != "none":
        return schema["sub_intents"].get(sub_intent, {}).get("required", [])
    return schema.get("required", [])
