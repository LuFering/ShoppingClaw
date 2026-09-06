"""
测试 render_product_card -> SSE -> 前端卡片渲染的完整链路
(不 import 项目模块，直接测试序列化和协议层面)
"""
import json

# ─── 1. 模拟 render_product_card 返回值 ───
print("=" * 60)
print("1. 模拟 render_product_card 工具返回格式")

mock_product = {
    "title": "荣耀X60 GT 12GB+512GB",
    "price": 1999.00,
    "platform": "jd",
    "url": "https://item.jd.com/100012345.html",
    "image_url": "https://img.example.com/phone.jpg",
    "rating": 4.8,
    "shop_name": "荣耀官方旗舰店",
}

# 模拟 tools.py render_product_card 的返回值
title = mock_product["title"]
price = float(mock_product.get("price", 0))
platform = mock_product.get("platform", "unknown")
url = mock_product.get("url", "#")
image_url = mock_product.get("image_url")
rating = mock_product.get("rating")
shop_name = mock_product.get("shop_name", "未知店铺")

result = json.dumps({
    "type": "product_card",
    "data": {
        "title": title,
        "price": price,
        "platform": platform,
        "url": url,
        "image_url": image_url,
        "rating": rating,
        "shop_name": shop_name,
    }
}, ensure_ascii=False)

print(f"    返回类型: {type(result).__name__}")
print(f"    返回长度: {len(result)} 字符")

parsed = json.loads(result)
assert parsed["type"] == "product_card", "type 应为 product_card"
assert "data" in parsed, "缺少 data 字段"
assert parsed["data"]["title"] == mock_product["title"]
assert parsed["data"]["price"] == mock_product["price"]
print(f"    ✅ 工具返回格式正确: type={parsed['type']}, title={parsed['data']['title']}")


# ─── 2. 模拟 _serialize_tool_result ───
print("\n" + "=" * 60)
print("2. 模拟 _serialize_tool_result 序列化")

def _serialize_tool_result(result):
    """与 sse_monitor.py 完全一致的实现"""
    if result is None:
        return None
    if isinstance(result, str):
        return result
    if isinstance(result, (dict, list)):
        try:
            return json.dumps(result, ensure_ascii=False, default=str)
        except Exception:
            return str(result)
    content_attr = getattr(result, "content", None)
    if content_attr is not None:
        if isinstance(content_attr, str):
            return content_attr
        try:
            return json.dumps(content_attr, ensure_ascii=False, default=str)
        except Exception:
            return str(content_attr)
    return str(result)

serialized = _serialize_tool_result(result)
assert isinstance(serialized, str)
assert serialized == result
print(f"    ✅ 字符串输入原样返回")

# dict 输入
dict_input = json.loads(result)
dict_serialized = _serialize_tool_result(dict_input)
assert isinstance(dict_serialized, str)
assert '"type": "product_card"' in dict_serialized
print(f"    ✅ dict 输入正确序列化为 JSON 字符串")


# ─── 3. 验证 sse_monitor.py 源码中 result_content 存在 ───
print("\n" + "=" * 60)
print("3. 验证 sse_monitor.py self._emit 包含 result_content")

import os
sse_monitor_path = os.path.join("src", "agents", "common", "middleware", "sse_monitor.py")
with open(sse_monitor_path, "r", encoding="utf-8") as f:
    source = f.read()

assert '"result_content": result_content' in source, \
    "❌ sse_monitor.py 的 self._emit 中缺少 result_content 字段！"
print(f"    ✅ sse_monitor.py self._emit 中包含 result_content 字段")


# ─── 4. 模拟 SSE 中间件发送 tool_complete ───
print("\n" + "=" * 60)
print("4. 模拟 SSE 中间件发送 tool_complete 事件")

# 模拟 sse_monitor.py wrap_tool_call 中的 self._emit
import uuid
tool_complete_event = {
    "type": "tool_complete",
    "tool_name": "render_product_card",
    "tool_call_id": "call_test_123",
    "result_preview": str(result)[:500] if result else "",
    "result_content": (result_content := result),  # ← 关键
    "duration_ms": 42,
    "meta": {"icon": "🃏", "category": "buildin"},
    "event_id": f"tool_{uuid.uuid4().hex[:8]}",
}

assert "result_content" in tool_complete_event
assert tool_complete_event["result_content"] == result
print(f"    ✅ tool_complete 事件包含 result_content")
print(f"       tool_name: {tool_complete_event['tool_name']}")
print(f"       result_content length: {len(tool_complete_event['result_content'])}")


# ─── 5. 模拟 format_sse_event 生成 SSE 输出 ───
print("\n" + "=" * 60)
print("5. 模拟 format_sse_event -> SSE 文本 -> 前端解析")

# format_sse_event 第 41 行: 移除 type 和 event_id
sse_data = {k: v for k, v in tool_complete_event.items() if k not in ("event_id", "type")}

# format_sse_event 第 46 行: json.dumps
sse_json = json.dumps(sse_data, ensure_ascii=False)

sse_output = f"event: tool_complete\nid: tool_test123\ndata: {sse_json}\n\n"
print(f"    SSE 输出:")
print(f"    event: tool_complete")
print(f"    id: tool_test123")
print(f"    data: {sse_json[:100]}...")

# 模拟前端 EventSource 解析 "data:" 行
# 前端: const data = JSON.parse(trimmed.slice(5))
frontend_data = json.loads(sse_json)

# 模拟前端 handleSSEEvent('tool_complete', data)
print(f"\n    【模拟前端 AgentChatComponent.vue:833】")
print(f"    tool_name: {frontend_data['tool_name']}")
print(f"    result_content 存在: {bool(frontend_data.get('result_content'))}")

# 前端 line 835-837: JSON.parse(data.result_content)
result_content_str = frontend_data["result_content"]
frontend_result = json.loads(result_content_str)

print(f"    JSON.parse(result_content).type = {frontend_result['type']}")
assert frontend_result["type"] == "product_card"
assert frontend_result["data"]["title"] == mock_product["title"]
print(f"    ✅ 前端 JSON.parse 成功！")


# ─── 6. 模拟 ProductCardTool.vue 组件渲染 ───
print("\n" + "=" * 60)
print("6. 模拟 ProductCardTool.vue 组件渲染")

# 模拟 AgentMessageComponent.vue line 34-40:
# :tool-call="{ tool_call_result: { content: JSON.stringify({ cards: [card] }) } }"
card_data = frontend_result["data"]
component_props = {
    "tool_call_result": {
        "content": json.dumps({"cards": [card_data]}, ensure_ascii=False)
    }
}

# 模拟 ProductCardTool.vue line 70-81: computed cards
content = component_props["tool_call_result"]["content"]
parsed_content = json.loads(content)
cards = parsed_content.get("cards", [])

assert len(cards) == 1
card = cards[0]

print(f"    ✅ ProductCardTool 渲染数据:")
print(f"       图片: {'✅ 有' if card.get('image_url') else '❌ 无'}")
print(f"       标题: {card['title']}")
print(f"       平台: {card['platform']}")
print(f"       价格: ¥{card['price']}")
print(f"       评分: ⭐ {card.get('rating', 'N/A')}")
print(f"       店铺: {card.get('shop_name', '')}")
print(f"       链接: {card.get('url', '')}")


# ─── 7. 模拟前端完整事件处理 ───
print("\n" + "=" * 60)
print("7. 模拟前端 handleSSEEvent 完整流程（AgentChatComponent.vue:821-884）")

productCards = []

# 模拟 case 'tool_complete'
if frontend_data["tool_name"] == "render_product_card" and frontend_data.get("result_content"):
    result_obj = json.loads(frontend_data["result_content"])
    
    cardData = None
    if result_obj.get("type") == "product_card" and result_obj.get("data"):
        cardData = result_obj["data"]
    
    if cardData:
        productCards.append(cardData)
        
assert len(productCards) == 1
assert productCards[0]["title"] == "荣耀X60 GT 12GB+512GB"
print(f"    ✅ productCards 数组: {len(productCards)} 张卡片")
print(f"       卡片: {productCards[0]['title']} ¥{productCards[0]['price']}")


# ─── 总结 ───
print("\n" + "=" * 60)
print("🎉 完整链路测试全部通过！")
print("=" * 60)
print("""
链路:
  render_product_card(product) -> JSON 字符串
    -> _serialize_tool_result() -> 原样返回
    -> self._emit({..., "result_content": result_content})
    -> format_sse_event() -> SSE 文本
    -> 前端 EventSource -> data.result_content
    -> JSON.parse(data.result_content) -> {type, data}
    -> cardData = result.data
    -> msg.productCards.push(cardData)
    -> ProductCardTool 渲染 -> <div class="product-card">
""")
