现在，重新审阅整个项目，参考 `d:\ShoppingClaw\docs` 的文档，分析项目进展。上述任务完成之后，我需要你帮助我开发 `d:\ShoppingClaw\src\agents\common\toolkits\buildin\tools.py` 文件。这个文件是 `d:\ShoppingClaw\src\agents\master_agent` 的内置工具，目前只是定义了几个工具，但没有完全开发。我需要你结合项目背景，帮我拟定一份 `d:\ShoppingClaw\src\agents\common\toolkits\buildin\tools.py` 这个文件的开发思路
### **1. 项目进展分析**
- **核心架构已就绪**：项目基于 `LangGraph` + `deepagents` 框架，采用了先进的中间件机制（如 `Filesystem`、`Memory`、`SubAgent`），主智能体（`MasterAgent`）已经具备了基本的协调能力。
- **数据库基础设施已搭建**：`PostgreSQL` 管理器（`pg_manager`）和基础业务模型（`User`）已经存在。
- **工具层处于早期阶段**：目前的 [tools.py](file:///d:/ShoppingClaw/src/agents/common/toolkits/buildin/tools.py) 仅包含了一些模拟（Mock）工具，尚未与真实的数据库和复杂的购物业务逻辑打通。

---

### **2. [tools.py](file:///d:/ShoppingClaw/src/agents/common/toolkits/buildin/tools.py) 开发思路拟定**

作为 `MasterAgent` 的内置工具包，该文件的核心目标是：**增强主 Agent 对用户状态的感知、对复杂任务的管理以及对子 Agent 的精准调度**。

#### **A. 记忆与画像工具（从模拟转向实战）**
- **思路**：完全抛弃内存中的 `_memory_store`，利用已有的 `PostgreSQL` 存储用户的长期偏好。
- **新增/改进工具**：
    - `update_user_preference`：实时将对话中提取的偏好（如“喜欢黑色”、“预算 5000 以内”）写入数据库。
    - `get_user_shopping_context`：为主 Agent 提供一个结构化的用户上下文，包含历史购买偏好、关注的品牌、以及当前的购物意图。

#### **B. 购物意图与任务管理工具（增强主 Agent 规划能力）**
- **思路**：主 Agent 需要将模糊的用户输入转化为清晰的任务指令，再分配给子 Agent。
- **建议新增工具**：
    - `extract_shopping_intent`：利用 LLM 解析用户的原始查询，提取关键参数（品类、预算范围、核心诉求、紧迫程度）。
    - `track_task_progress`：记录当前购物任务的阶段（如：需求确认 -> 全网搜集 -> 对比分析 -> 最终推荐），方便主 Agent 在中断恢复后能继续任务。

#### **C. 人机协同与中断处理（深度利用 LangGraph `interrupt`）**
- **思路**：目前的 `ask_user_question` 已经使用了 `interrupt`，但可以更进一步。
- **建议改进**：
    - **结构化反馈**：支持更复杂的交互类型，如“确认搜索关键词”、“选择对比维度（价格/性能/评价）”。
    - **异常处理辅助**：当子 Agent（如爬虫）遇到验证码或网络错误时，通过此工具请求用户干预。

#### **D. 数据展示与格式化工具（提升用户体验）**
- **思路**：子 Agent 返回的数据往往是原始的 JSON，主 Agent 需要工具将其转化为易读的 Markdown 或结构化卡片。
- **建议新增工具**：
    - `render_product_card`：将商品数据转化为 Streamlit 前端可以直接渲染的标准卡片格式。
    - `format_comparison_table`：对比多个商品时，生成整齐的 Markdown 对比表。

---

### **3. 后续开发计划建议**

1.  **第一步：打通数据库**。将 [tools.py](file:///d:/ShoppingClaw/src/agents/common/toolkits/buildin/tools.py) 中的 `save_user_preference` 和 `get_user_profile` 改为使用 `pg_manager` 进行真实存储。
2.  **第二步：强化意图提取**。开发 `extract_shopping_intent`，让主 Agent 变得更聪明，不再只是简单的复读机。
3.  **第三步：子 Agent 联动**。在 `MasterAgent` 的逻辑中，通过工具获取子 Agent 的状态，实现更精准的派发。

