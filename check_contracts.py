#!/usr/bin/env python3
"""Contract validation checks for post_purchase agent."""
import sys
sys.path.insert(0, "/home/ubuntu/ShoppingClaw")

# Check if the test can at least parse the YAML and check constants
import yaml
with open("src/agents/subagents/subagents.yaml", "r", encoding="utf-8") as f:
    cfg = yaml.safe_load(f)

POST_TOOLS = [
    "get_user_shopping_context",
    "save_user_preference",
    "recall_past_decisions",
    "get_user_profile",
]

yaml_tools = cfg["post_purchase"]["tools"]
assert yaml_tools == POST_TOOLS, f"YAML tools mismatch: {yaml_tools}"
print("✅ YAML tool binding matches expected")

# Check discovery.py content
with open("src/agents/common/toolkits/discovery.py", "r", encoding="utf-8") as f:
    disc_content = f.read()

for tool in POST_TOOLS:
    assert tool in disc_content, f"Tool {tool} not found in discovery.py"
print("✅ discovery.py contains all post_purchase tools")

# Check chat_stream_service.py
with open("src/services/chat_stream_service.py", "r", encoding="utf-8") as f:
    css_content = f.read()

assert "_SUBAGENT_PLANNED_TOOLS" in css_content
assert "post_purchase" in css_content
for tool in POST_TOOLS:
    assert tool in css_content, f"Tool {tool} not found in chat_stream_service.py"
print("✅ chat_stream_service.py contains all post_purchase tools")

# Check subagents.py has fallback function
with open("src/agents/common/middleware/subagents.py", "r", encoding="utf-8") as f:
    sub_content = f.read()

assert "def _insufficient_data_fallback" in sub_content
assert "_insufficient_data_fallback(subagent_type)" in sub_content
print("✅ subagents.py has schema-aware fallback function")

print("\n🎉 All contract checks passed!")
