"""Parse docker log and analyze time bottlenecks"""
import re
from datetime import datetime

log = open("/proc/self/fd/0").read() if False else """2026-05-15 10:09:40,109 - config
2026-05-15 10:09:43,247 - model_1_end  (3.1s)
2026-05-15 10:09:43,254 - tool_get_context
2026-05-15 10:09:43,365 - model_2_start
2026-05-15 10:09:45,710 - model_2_end  (2.3s)
2026-05-15 10:09:45,763 - model_3_start
2026-05-15 10:10:02,767 - model_3_end  (17s!)
2026-05-15 10:10:02,782 - tool_get_profile
2026-05-15 10:10:02,796 - model_4_start
2026-05-15 10:10:09,722 - model_4_end  (7s)
2026-05-15 10:10:09,729 - dispatch_researcher
2026-05-15 10:10:12,313 - jd_search_1  (2 searches)
2026-05-15 10:10:20,765 - jd_detail_batch_1 (6 details)
2026-05-15 10:10:25,631 - jd_detail_batch_2 (5 more)
2026-05-15 10:10:36,606 - jd_search_3
2026-05-15 10:10:45,845 - jd_batch_specs (10 specs)
2026-05-15 10:10:49,584 - jd_search_4 (2 searches)
2026-05-15 10:10:56,526 - jd_search_5 (2 searches)
2026-05-15 10:11:17,513 - model_5_start
2026-05-15 10:11:26,885 - model_5_end  (9s)
2026-05-15 10:11:26,912 - model_6_start
2026-05-15 10:11:33,656 - model_6_end  (7s)
2026-05-15 10:11:33,669 - dispatch_analyst
2026-05-15 10:11:37,449 - analyst_knowledge
2026-05-15 10:11:46,910 - analyst_extract_specs (9.5s)
2026-05-15 10:12:05,588 - analyst_filter
2026-05-15 10:12:39,377 - client_disconnect"""

# Actually read from docker logs
import subprocess
result = subprocess.run(
    ["docker", "logs", "shoppingclaw-api", "--tail", "200"],
    capture_output=True, text=True
)
lines = result.stdout

# Extract all INFO/RERROR/WARNING with timestamps
pattern = re.compile(r'(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),(\d{3})')

entries = []
for i, line in enumerate(lines.split('\n')):
    m = pattern.search(line)
    if m:
        ts_str = m.group(1) + '.' + m.group(2)
        dt = datetime.strptime(ts_str, '%Y-%m-%d %H:%M:%S.%f')
        entries.append((dt, line[:120]))

# Calculate gaps
print("=== Time bottlenecks (>2s) === ")
for i in range(1, len(entries)):
    delta = (entries[i][0] - entries[i-1][0]).total_seconds()
    if delta > 2:
        label = entries[i][1].strip()
        print(f'+{delta:5.1f}s  {label}')

print()
print("=== Summary ===")
# Count model calls
model_nodes = sum(1 for _, l in entries if '>>> 进入model节点' in l)
print(f"Model (DeepSeek) calls: {model_nodes}")
# Count JD API inits
jd_inits = sum(1 for _, l in entries if 'JD API' in l)
print(f"JD API SDK re-initializations: {jd_inits}")
# Count searches
searches = sum(1 for _, l in entries if '整合搜索' in l)
print(f"JD searches: {searches}")
# Count product details
details = sum(1 for _, l in entries if '获取商品完整详情' in l)
print(f"Product detail fetches: {details}")
