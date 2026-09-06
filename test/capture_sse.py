"""抓取 SSE 流，查找 tool_complete 事件中是否有 render_product_card"""
import requests, json, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

BASE = "http://localhost:5050"

# 1. 登录
print("[1] 登录...")
r = requests.post(f"{BASE}/api/auth/token",
    data={"username": "admin", "password": "admin123"})
if r.status_code != 200:
    print(f"FAIL: {r.status_code} {r.text}")
    sys.exit(1)
token = r.json()["access_token"]
print(f"   OK, token={token[:30]}...")

# 2. 获取 agent
print("[2] 获取 agent...")
r = requests.get(f"{BASE}/api/chat/agent", headers={"Authorization": f"Bearer {token}"})
agents = r.json()["agents"]
agent_id = agents[0]["id"]
print(f"   agent_id={agent_id}")

# 3. 发送商品推荐消息（触发 render_product_card）
import uuid
thread_id = f"sse-capture-{uuid.uuid4().hex[:8]}"
query = "推荐几款2000元左右的5G手机，要性价比高的，请用render_product_card工具渲染卡片"

print(f"[3] 发送聊天: thread_id={thread_id}")
print(f"   query={query}")

r = requests.post(
    f"{BASE}/api/chat/agent/{agent_id}",
    headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    },
    json={"query": query, "config": {"thread_id": thread_id}, "meta": {}},
    stream=True,
    timeout=300,
)

print(f"   Status: {r.status_code}")
if r.status_code != 200:
    print(f"   FAIL: {r.text[:500]}")
    sys.exit(1)

# 4. 解析 SSE 流
print("[4] 解析 SSE 流...")
tool_complete_events = []
all_event_types = set()
current_event = None
line_count = 0

for line_bytes in r.iter_lines():
    if not line_bytes:
        continue
    try:
        line = line_bytes.decode('utf-8').strip()
    except:
        continue
    
    line_count += 1
    if line.startswith("event:"):
        current_event = line[6:].strip()
        all_event_types.add(current_event)
    elif line.startswith("data:"):
        try:
            data = json.loads(line[5:])
        except:
            continue
        
        if current_event == "tool_complete":
            tool_complete_events.append({
                "event": current_event,
                "tool_name": data.get("tool_name", ""),
                "has_result_content": "result_content" in data,
                "result_content_len": len(data.get("result_content", "")),
                "result_preview": str(data.get("result_preview", ""))[:100],
                "full_data": data,
            })
            print(f"   TOOL_COMPLETE: tool={data.get('tool_name')}, "
                  f"has_result_content={'result_content' in data}, "
                  f"rc_len={len(data.get('result_content', ''))}")

print(f"\n[5] 统计:")
print(f"   总行数: {line_count}")
print(f"   事件类型: {sorted(all_event_types)}")
print(f"   tool_complete 事件数: {len(tool_complete_events)}")

# 重点检查 render_product_card
rp_events = [e for e in tool_complete_events if e["tool_name"] == "render_product_card"]
print(f"   render_product_card 事件数: {len(rp_events)}")

for i, evt in enumerate(rp_events):
    print(f"\n--- render_product_card #{i+1} ---")
    print(f"   has_result_content: {evt['has_result_content']}")
    print(f"   result_content_len: {evt['result_content_len']}")
    if evt["has_result_content"]:
        rc = evt["full_data"].get("result_content", "")
        try:
            parsed = json.loads(rc)
            print(f"   parsed type: {parsed.get('type')}")
            print(f"   data keys: {list(parsed.get('data', {}).keys())}")
        except:
            print(f"   [无法解析 result_content] {rc[:100]}")

print("\n=== 完成 ===")
