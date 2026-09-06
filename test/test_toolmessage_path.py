import sys, json, io
sys.path.insert(0, ".")
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

from langchain_core.messages import ToolMessage

product_card_json = json.dumps({
    "type": "product_card",
    "data": {"title": "Xiaomi Redmi K80", "price": 1999.0, "platform": "jd",
             "url": "https://example.com/12345", "image_url": "https://img.example.com/k80.jpg",
             "rating": 4.8, "shop_name": "Xiaomi Official Store"}
}, ensure_ascii=False)

tool_msg = ToolMessage(content=product_card_json, tool_call_id="test_call_001", name="render_product_card")

def make_chunk(**kw):
    return {"request_id": "test-001", **kw}

chunk = make_chunk(
    status="thinking_process", event="tool_result",
    tool_call={
        "tool_call_id": tool_msg.tool_call_id,
        "function": tool_msg.name, "name": tool_msg.name, "args": {},
        "content": tool_msg.content, "output": tool_msg.content, "status": "completed",
        "duration_ms": 100, "tool_meta": {"icon": "card", "category": "display"},
        "icon": "card",
    })

from src.services.sse_adapter import convert_legacy_chunk_to_sse

sse_events = convert_legacy_chunk_to_sse(chunk)
print(f"Number of SSE events: {len(sse_events)}")
for i, sse in enumerate(sse_events):
    print(f"\n--- Event {i} ---")
    print(repr(sse[:500]))
    print("---")
    if "TOOL_COMPLETE" in sse:
        print("  >>> CONTAINS TOOL_COMPLETE!")
    if "result_content" in sse:
        print("  >>> CONTAINS result_content!")
