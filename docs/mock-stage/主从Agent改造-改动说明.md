# 主从 Agent 改造 — 改动说明与待决事项

> 状态：**代码已改完（本地），未部署**。改动前原文件备份在 `_backup_20260914/`。
> 依据：`后端改造规划.md` §1、§2、§3.2、§4 + 你 2026-09-14 的 6 条答复 + 后续「走 Skill」的决定。

---

## 一、本轮做了什么

**范围**：只做「主从 agent 改造」。代购送礼、采购规划、主动服务、风险政策 RAG、决策库后端**全部按你的要求搁置**。

| 文件 | 行数变化 | 改动要点 |
|---|---|---|
| `src/agents/master_agent/graph.py` | +123 / −4 | 工具下移改白名单；透传 `display_name`；为子智能体挂 Skills middleware |
| `src/agents/subagents/subagents.yaml` | +132 / −195 | 4 个子智能体 → 2 个；两个子智能体工具表加 `read_skill`，prompt 加技能使用规范 |
| `src/agents/master_agent/BASE_PROMPT.md` | +9 / −5 | SubAgent 表 4 → 2，新增调度收敛规则 |
| `src/agents/common/middleware/subagents.py` | +17 / −0 | `display_name` 贯通到 6 处 SSE 事件 |
| `src/agents/common/toolkits/__init__.py` | +3 / −0 | 加载时注册 `read_skill` 工具 |
| `docker/api.Dockerfile` | +5 / −0 | `COPY skills/ /app/skills/` |
| `.dockerignore` | +6 / −0 | 放行 `skills/**`（否则 `*.md` 规则会滤掉 SKILL.md） |
| `docker-compose.yml` | +3 / −0 | api 服务挂 `./skills:/app/skills` |

新增文件（git 未跟踪）：

| 路径 | 内容 |
|---|---|
| `skills/pre_purchase/*/SKILL.md` | 4 个购前技能正文 |
| `skills/post_purchase/*/SKILL.md` | 3 个购后技能正文 |
| `src/agents/common/toolkits/skills/tools.py` | `read_skill` 工具 + `get_skills_root()` |
| `src/agents/common/toolkits/skills/__init__.py` | 导出上述两个符号 |

> 行数说明：`.dockerignore` 的 `git diff --numstat` 会显示 83/77，那 90% 是 CRLF/LF 行尾噪声（tar 从服务器回传时丢失了行尾约定）。**加 `--ignore-cr-at-eol` 后真实改动就是 +6 / −0**。功能无影响。

### 1. 工具下移（§1.1）

原来主智能体是按**类目**过滤工具的：

```python
category == "buildin"   # 把 5 个领域工具一起留在了主上下文
```

改成**显式白名单**：

```python
_MASTER_TOOL_ALLOWLIST = {
    "render_product_card",      # 出卡交付
    "format_comparison_table",  # 对比表格交付
    "ask_user_question",        # 澄清（仍被 _deprecated 过滤，实际不暴露）
    "track_task_progress",      # 编排：进度
}
```

**实际效果**：主智能体工具从 8 个（9 个 buildin 减去已弃用的 `ask_user_question`）降到 **3 个**。

> 说明：这里没有改动各工具的 `category` 元数据，理由有二 ——
> ① `category` 会被 `sse_monitor` 透出到 SSE，改它可能影响前端；
> ② 下移只需要「不挂到主智能体」，子智能体取工具走的是 `_get_tool_by_name()`（按名字查全局注册表，**与 category 无关**），所以白名单是最小改动。
>
> 下移去向：`price_calculator` → 购前；`get_user_shopping_context` / `get_user_profile` / `recall_past_decisions` / `save_user_preference` → 购后。

### 2. 子智能体 4 → 2（§2）

| 新名称 | display_name | 由谁合并 | 工具 |
|---|---|---|---|
| `pre_purchase` | **选购顾问** | researcher + analyst + critic | 8 个（搜索 / 详情 / 批量规格 / 规格提取 / 条件过滤 / 品类知识 / 风控规则 / 价格计算） |
| `post_purchase` | **持有管家** | memory_manager（扩展为持有+售后+维护+复购） | 4 个（购物上下文 / 用户画像 / 历史决策 / 保存偏好） |

- YAML 里引用的 **12 个工具名已逐个校验存在**，且这些工具都没有 `name=` 覆盖，函数名即工具名。
- `post_purchase` 尚未实现的 4 个工具（`read_decisions` / `write_decisions` / `write_experience_review` / `query_warranty`）以**注释**占位，等决策库后端落地后再打开。

### 3. 主智能体 Prompt（§1.2）

- SubAgent 能力边界表 4 行 → 2 行，改用中文名（选购顾问 / 持有管家）。
- 新增 **「单域请求自己答，跨域才调度」** —— 能自己答的别外包，需要外部数据才派发。
- 新增 **「跨域任务要分开派」** —— 同时需要商品+画像时并行发两个 `task`，不要塞进一个 description。
- 保留你之前已修好的三条（正文①硬性要求、禁止重复调度、收敛≠省略交付）。

### 4. `task` → 中文显示名（§4，后端侧）

- `_SubagentSpec` 增加 `display_name`；`_get_subagents_legacy()` / `_get_subagents()` 两条路径都透传；`general-purpose` 固定给「通用助手」。
- `_build_task_tool()` 建 `subagent_display_names` 映射，**6 处 SSE 事件**（started / retry / completed × 同步+异步）全部补上 `subagent_name` 字段。

> 顺带发现：前端 `TaskTool.vue` 的取值链是
> `subagent_run.subagent_name → display_label → parsedArgs.subagent_type → '子智能体'`，
> 而 `src/`、`server/` 里**一个都没有**（`sse_adapter.py` 里连 subagent 字样都没有）。
> 所以前端那套是照搬 Yuxi 的死代码，**现在用户看到的就是英文 slug** —— 这正是规划里说的红线问题。
> 本次补了 `subagent_name`，但**「SSE 事件 → 前端 toolCall → subagent_run」这段中间链路是否有环节丢弃该字段，我还没验证**，需要跑一次真实对话确认。

### 5. 领域方法论 Skill 落地（§3.2）

按你的判断：工具负责「执行某项任务」，Skill 负责「擅长某个领域的技巧」。所以方法论做成 Skill，工具只保留取数、算价这类确定性动作。

#### 5.1 技能清单（9 个 = 6 购前 + 3 购后）

| 子智能体 | 分组目录 | 技能（slug → 中文） |
|---|---|---|
| `pre_purchase`（选购顾问） | `skills/pre_purchase/` | `clarifying-needs` 需求澄清 · `evaluating-fit` 单品适配 · `comparing-products` 对比择优 · `hunting-deals` 比价优惠 · `checking-compatibility` 搭配兼容 · `screening-risks` 风险排雷 |
| `post_purchase`（持有管家） | `skills/post_purchase/` | `reviewing-holdings` 持有盘点 · `handling-after-sales` 售后保修 · `planning-maintenance` 维护换新 |

`gift-picking` / `purchase-planning` 属独立 Agent，本轮**未创建**。

#### 5.2 这一轮优化了什么（依据公开规范 + 行业能力清单）

对照 Anthropic《Skill authoring best practices》与电商 AI 助手的能力拆解（Discovery → Consideration → Purchase → Post-purchase），原 7 个技能有 3 类问题，已逐条修掉。

**① 能力空洞：购前缺了最上游的两环**

原 7 个技能全都假设「用户已经知道自己要什么」。但行业能力清单里最核心的一环恰恰是**意图理解** —— 把「想要个安静的」「送长辈的」这类模糊表达转成可执行条件。`product-compare` 自己的正文就写着「不适用于只有一个候选」，而单品评估也恰好没有对应技能。这两个洞正是用户最高频的入口，已补为：

- `clarifying-needs` —— 需求澄清与转译：必选/加分/否决三级分层、追问与不问的边界、停止追问的时机。
- `evaluating-fit` —— 单品适配度评估：逐条比对、价格合理性、「能买 / 有条件能买 / 该继续找」三选一收口。

**② 命名不统一（违反规范的显式条目）**

规范要求同一技能集合内命名模式一致、优先动名词、禁止缩写。原命名是名词/动名词混杂，`bundle-compat` 还用了缩写。已统一为动名词：

| 旧名 | 新名 |
|---|---|
| `product-compare` | `comparing-products` |
| `deal-hunting` | `hunting-deals` |
| `bundle-compat` | `checking-compatibility` |
| `risk-screening` | `screening-risks` |
| `holding-review` | `reviewing-holdings` |
| `warranty-service` | `handling-after-sales` |
| `maintenance-reminder` | `planning-maintenance` |

旧目录整体移到 `_backup_20260915/skills_before_rename/`（可逆），没有硬删除。

**③ 结构不符合最佳实践**

| 问题 | 改法 |
|---|---|
| 关键红线埋在正文中后段 | 抽成正文首行的**核心原则**（规范：critical instructions at top） |
| 「验收方式」是静态清单，不构成反馈回路 | 改为 **交稿前自检** 的可勾选清单（规范推荐的 checklist 模式） |
| description 缺具体触发语 | 补全用户会说的原话（「选哪个 / 值不值 / 该修还是该换」）+ 负向触发 + 替代技能指向 |
| 技能间交叉引用易失效 | 全部重写为新 slug，并加校验脚本防悬空引用 |

正文 47–65 行（规范上限 500），description 100–171 字符（上限 1024）。

#### 5.3 加载机制：渐进披露，正文不进常驻上下文

- `SkillsMiddleware` 在 `before_agent` 只扫 `*/SKILL.md` 的 frontmatter，把「名字 + 用途」注入 system prompt —— **不注入正文**。
- 模型判断任务相关时再调 `read_skill(skill="comparing-products")` 取回正文，然后按步骤执行。
- 提示模板已注明**一个任务可能串行需要多个技能**（先澄清需求 → 再择优 → 后排雷），避免只读一个就动手。

#### 5.4 为什么自造 `read_skill`，而不用现成的文件工具

- 子智能体原本**没有任何文件工具**（`FilesystemMiddleware` 只挂主智能体）。要用 `read_file` 就得给每个子智能体补挂 `FilesystemMiddleware` —— 一次带进 6 个通用文件工具并开放任意路径读写，上下文和安全都不划算。
- `read_skill` 只做一件事：按 slug 从 `skills/` 里读一个 SKILL.md 正文。1 个工具、目录只读、slug 正则校验、阻断路径穿越，20000 字符上限。

#### 5.5 部署配套（三条缺一不可）

1. `docker/api.Dockerfile` → `COPY skills/ /app/skills/`。
2. `.dockerignore` → 必须加 `!skills` 与 `!skills/**`。**最容易踩的坑**：第 53 行的 `*.md` 规则会把所有 SKILL.md 一并忽略，`COPY` 只拷进去空目录 → 生产 `read_skill` 永远命中不到。
3. `docker-compose.yml` → api 服务挂 `./skills:/app/skills`，线上改技能无需重建镜像。

#### 5.6 本地已验证

- 9 份 SKILL.md：frontmatter 可解析、`name` 与目录名一致、slug 规范、name ≤64 字符、description ≤1024 字符且为第三人称、正文 <500 行、均含自检清单。
- 交叉引用：无悬空引用、无旧名残留。
- `subagents.yaml` 可解析（pre_purchase 9 个工具 / post_purchase 5 个工具）。
- **未验证**：容器内 `/app/skills` 是否可读（需部署确认）、模型在真实对话里是否会**主动**调 `read_skill`、以及新补的两个技能能否被正确触发。

#### 5.7 资源层与脚本层已接通（references/ + scripts/）

Anthropic 规范里 Skill 是**文件夹**：`SKILL.md` 是唯一必需文件，`references/`、`scripts/`、`assets/` 是可选的资源层（渐进披露的第二层）。原实现只接通了「指令层」。**现在四层全部可用**：

```
skills/<group>/<slug>/
    SKILL.md            必需：方法论正文
    references/*.md     可选：补充资料（清单 / 矩阵 / 规则表）
    assets/*            可选：模板与素材
    scripts/*.py|*.sh   可选：可执行脚本        ← 本轮新增
```

**两个工具，各做一件事**

| 工具 | 作用 |
|---|---|
| `read_skill(skill, file=None)` | 不带 `file` → 返回 SKILL.md 正文，**并在末尾列出该技能附带的所有文件清单**；带 `file` → 读取指定文件（`references/`、`assets/` 下的文本，或 `scripts/` 下的脚本源码） |
| `run_skill_script(skill, script, args=None)` | **执行** `scripts/` 下的 `.py` / `.sh`（本轮新增） |

正文末尾自动列清单这一步很关键：否则模型不知道技能里带了哪些文件，资源加了也发现不了。

**安全约束**（白名单硬校验，不放开任意路径）

- 读取：路径须匹配 `(references|assets)/….{md,txt,json,csv,yaml}` 或 `scripts/….{py,sh,js,md,txt,json,csv,yaml}`。
- 执行：路径须匹配 `scripts/….{py,sh}`，且必须在脚本发现清单内。
- `..`、绝对路径、其他目录一律拒绝；解析后再做一次 `is_relative_to(skill_root)` 双保险。
- 读取上限 20000 字符、脚本输出上限 20000 字符。

**脚本执行的安全设计**（`src/agents/common/toolkits/skills/tools.py` 模块头有完整说明）

| 措施 | 说明 |
|---|---|
| 技能目录随镜像发布、**不接受运行时上传** | `scripts/` 下的文件都是仓库作者写的，属可信资产 |
| **不用 shell**（`shell=False` + 参数列表） | 不存在命令注入 |
| **不继承环境变量** | 只注入 `PATH` / `PYTHONIOENCODING` / `PYTHONDONTWRITEBYTECODE` / `LC_ALL`；DB 连接串与第三方 API Key 读不到 |
| 超时 30 秒、输出截断 | 防止脚本挂死或刷屏 |
| 参数只收字符串列表、拒绝 NUL | 参数无法越权 |
| **已知局限** | 无网络隔离、无文件系统隔离 —— 因此脚本只做确定性计算，不写文件、不联网。若将来要跑不可信脚本，必须换成容器沙箱（`BaseSandbox` 子类） |

**已落地的脚本**

| 技能 | 脚本 | 作用 |
|---|---|---|
| `handling-after-sales` | `scripts/after_sales_window.py` | 由签收日算 7 天 / 15 天 / 保修期各截止日与剩余天数 |
| `planning-maintenance` | `scripts/next_replacement.py` | 由上次更换日 + 周期算下次到期日与建议提醒日 |

这两份正好补上了 `price_calculator` 的短板 —— **它只支持四则运算（正则限定 `[0-9+\-*/().]`），算不了日期**。以前这类日期全靠模型心算，现在变成确定性的、可复现的。两份脚本都是纯标准库（`argparse` + `datetime`），不引入依赖、不写文件、不联网。

**试点**：给 `checking-compatibility` 加了 `references/category-field-matrix.md`（11 个品类的核对字段 + 典型踩坑 + 跨品类收口清单）。SKILL.md 正文保持 47 行不变，只在需要具体品类细节时才读矩阵。

**为什么其它 8 个技能没加资源层**：诚实评估后，只有 `checking-compatibility` 与 `screening-risks` 属于真正的「查表型」内容，其余都是判断方法论，正文 50 行已能自洽，拆出去只会多一次读取。**不为"看起来像标准 Skill"而堆文件。**

**顺带说明：日期计算这个缺口，暂不补工具。** `price_calculator` 确实只支持四则运算、算不了日期，但 `planning-maintenance` 本来就明确要求"不要给出精确到天的假精确"（给区间不给点值），所以现在并不真的需要日期工具。等将来要做"精确到期提醒"时，再做工具，不要现在提前造。

#### 5.8 本轮实测结果

| 用例 | 结果 |
|---|---|
| 读普通技能正文 | ✅ 正常 |
| 读带资源的技能 | ✅ 正文末尾附资源清单 |
| 读 `references/…md` | ✅ 正常返回 |
| `../../` 越界 | ✅ 拒绝 |
| 绝对路径 `/etc/passwd` | ✅ 拒绝 |
| 非白名单目录 `secret/a.md` | ✅ 拒绝 |
| 非法扩展名 `.py` | ✅ 拒绝 |
| `scripts/x.py` | ✅ 拒绝并说明原因 |
| 不存在的资源文件 | ✅ 提示不存在 |
| 不存在的技能名 / 非法 slug | ✅ 列出可用技能 / 提示格式 |

#### 5.9 能力边界（本轮更新后）

**agent 现在能拿到的**

| 能力 | 入口 | 范围 |
|---|---|---|
| 读方法论正文 | `read_skill(skill)` | `SKILL.md`（frontmatter 已剥离） |
| 读补充资料 / 脚本源码 | `read_skill(skill, file=…)` | `references/`、`assets/` 下的文本；`scripts/` 下的 `.py/.sh/.js` |
| **执行脚本**（本轮新增） | `run_skill_script(skill, script, args)` | `scripts/` 下的 `.py` / `.sh` |

**仍然拿不到的**：二进制资源（图片 / 字体 / pptx / xlsx）、技能目录以外的任何文件、任意 shell、网络访问。

**背景：仓库里那套通用「Sandbox 执行链条」仍然是断的，且是刻意保留不给技能用的**

排查时发现仓库里还有另一套通用执行链路（与技能无关、未接线）：

| 零件（已存在） | 位置 | 作用 |
|---|---|---|
| `SandboxBackendProtocol` | `backends/protocol.py` | 声明 `execute()` / `aexecute()` |
| `BaseSandbox` | `backends/sandbox.py` | 抽象基类：只要实现 `execute()`，全部文件操作自动获得 |
| `LocalShellBackend` | `backends/local_shell.py` | 可直接跑 shell（已在 `backends/__init__.py` 导出） |
| `FilesystemMiddleware._supports_execution()` | `middleware/filesystem.py:246` | **backend 实现协议 → 自动挂一个 `execute` 工具** |

**三处断点：**

1. 主智能体接的是 `FilesystemMiddleware(backend=_create_fs_backend)`，而 `_create_fs_backend` 返回 `StateBackend(runtime)` —— `StateBackend` 不实现 `SandboxBackendProtocol`，所以 `_supports_execution()` 为假，**`execute` 工具根本不会被创建**。
2. 子智能体的 `default_middleware` 里没有 `FilesystemMiddleware`，**连文件工具都没有**，更谈不上执行。
3. 唯一现成的执行后端 `LocalShellBackend` 是**无沙箱的主机 shell**：`subprocess.run(shell=True)`，不隔离、不限资源、可读任意密钥、`virtual_mode` 对 shell 无效。**它自己的 docstring 就写明"生产环境不适用"。**

**另一处死代码**：`repositories/skill_repository.py` + `Skill` 模型已经带了 `tool_dependencies` / `mcp_dependencies` / `skill_dependencies` 三个字段 —— 这正是参考架构 Yuxi 的技能模型（Yuxi 的 `resolve_skill_gated_tools()` 会把技能声明的工具注册进 ToolNode）。**但本仓库没有任何地方引用它。**

**与 Yuxi 的差距（已逐行核实）**：Yuxi 的 skill = `SKILL.md` + `scripts/` + DB 声明的依赖。它的**读取**走 deepagents 的通用 `read_file`（读虚拟路径 `/home/gem/skills/<slug>/SKILL.md`），`SkillsMiddleware.wrap_tool_call` 拦截这次读 → 解析出 slug → 写入 `activated_skills`（**读即激活**）。它的**执行**靠**工具门控**：技能声明的 `tool_dependencies`（如 `terminal`）在未激活时**对模型隐藏**，激活后才加回 `model_tools`；`terminal` 落在远程沙箱后端（`deepagents` 的 `BaseSandbox` 子类 + HTTP provisioner，每线程一个沙箱），于是能 `cd /home/gem/skills/<slug> && uv run scripts/query.py`。

本仓库把 `BaseSandbox` 搬了过来，但**没搬 sandbox provider、没搬技能工具门控、也没接 `Skill` 表**。**其中最值得借鉴的是「工具门控」** —— 它才让"技能＝能力包"成立：技能不仅告诉模型怎么做，还能决定模型能用哪些工具。**该机制本轮已实现，见 §5.11。**

> **结论**：现在"只能读文本"是**移植时的能力裁剪**，不是设计结论。要真正具备执行力，需要：① 接一个实现 `SandboxBackendProtocol` 的 backend（`execute` 工具会自动出现，middleware 不用改）；② 该 backend 必须真正隔离（**不能用 `LocalShellBackend`**）；③ 复活技能的工具依赖声明。

#### 5.10 决策记录（2026-09-15）：技能是能力包，不只是提示词

最初曾决定「技能维持方法论定位、不引入执行」，**该决策当天被否决**：如果技能只能读 markdown 文件，那它本质上只是一个可路由的提示词，不算 skill。修正后的决策：

- **技能 = 能力包**：`SKILL.md` + `references/` + `scripts/` + **工具门控声明**，四层全部接通。
- **执行方式**：走**受限脚本通道**（`run_skill_script`：白名单 + 无 shell + 不继承环境变量 + 超时 + 输出截断），而不是接通通用沙箱。
- **工具门控**：技能用 `tools:` 声明自己解锁哪些工具，未激活时这些工具对模型隐藏。见 §5.11。

**保留不变的（仍是刻意的死代码，勿误以为已成能力）**

| 项 | 状态 |
|---|---|
| `backends/local_shell.py`（`LocalShellBackend`） | 未接线；无沙箱，生产不可用 |
| `backends/sandbox.py`（`BaseSandbox`） | 未接线；留作将来做真正隔离沙箱的基类 |
| `repositories/skill_repository.py` + `Skill` 表 | 未接线（`tool_dependencies` 等字段无引用；我们用 frontmatter 的 `tools:` 代替） |
| 主智能体 `FilesystemMiddleware` 的 backend | 继续接 `StateBackend`（因此没有 `execute` 工具）；它也用不到技能脚本 |

**升级路径（触发条件）**：如果将来要跑**不可信**脚本、或需要网络/文件系统隔离，则改为实现 `BaseSandbox` 子类（容器执行），把 `run_skill_script` 切到该后端上即可 —— 接口不变，只换执行器。

#### 5.11 工具门控：技能现在能决定「模型能用哪些工具」

这是对齐 Yuxi 的核心机制，也是让「技能＝能力包」真正成立的一环。此前工具是子智能体级静态配置，技能对工具可见性零影响。

**机制**

1. 技能在 frontmatter 用 `tools:` 声明自己「解锁」的工具：

   ```yaml
   name: hunting-deals
   tools:
     - price_calculator
   ```

2. `SkillsMiddleware` 启动时把这些声明汇总成**门控集合**（所有技能声明的并集）。
3. 每次模型调用前（`modify_request`）计算 `隐藏 = 门控集合 − 已激活技能解锁的工具`，把「隐藏」里的工具从 `request.tools` 中剔除 —— **对模型不可见**。
4. **读即激活**：`wrap_tool_call` / `awrap_tool_call` 拦截 `read_skill` 与 `run_skill_script` 调用，从参数里取出 `skill` slug，写进 state 的 `activated_skills`（保序去重 reducer）。下一次模型调用时，该技能解锁的工具就出现了。

**关键点：门控只影响「模型看得见什么」，不影响「能不能执行」** —— 被隐藏的工具仍绑定在子智能体上，只是不出现在模型的工具 schema 里。

**本轮声明的门控**

| 技能 | 解锁工具 |
|---|---|
| `hunting-deals`、`checking-compatibility` | `price_calculator` |
| `screening-risks` | `query_risk_policy` |
| `handling-after-sales`、`planning-maintenance` | `run_skill_script` |

**刻意只门控这 3 个工具**，不动 `search_products` / `get_products_specs_extract` / `query_category_knowledge` 等主干工具 —— 门控过度会伤主流程。未声明 `tools:` 的技能不产生任何门控，所以对既有技能零影响。

**顺带修掉一个误导**：上游 `_format_skills_list` 会输出 `-> Read \`<path>\` for full instructions`，但我们子智能体没有文件工具、读不到那个路径。已改为 `-> 读取方式：read_skill(skill="<name>")`（新增 `skill_read_hint` 属性，可覆盖）。

**状态隔离**：`activated_skills` 加进了 `SubAgentMiddleware._EXCLUDED_STATE_KEYS`，既不会从父智能体继承进来，也不会回传给父智能体 —— 它是每个子智能体各自的局部状态。

**已验证（单元测试）**

| 用例 | 结果 |
|---|---|
| 未激活任何技能 | 7 个工具中隐藏 `price_calculator`、`query_risk_policy`、`run_skill_script` |
| 读 `hunting-deals` | `price_calculator` 解锁（其余仍隐藏） |
| 读 `screening-risks` | `query_risk_policy` 解锁 |
| 读 `handling-after-sales` | `run_skill_script` 解锁 |
| 读完 4 个声明工具的技能 | 全部可见 |
| `read_skill` 带 `file=` 参数 | 同样触发激活 |
| 未知技能名 | 拒绝激活并打 warning |
| 非激活类工具调用 | 不激活 |
| 重复激活 | reducer 保序去重 |

**未验证**：真实对话里模型能否正确「先读技能、再用工具」；被隐藏的工具是否会让模型困惑（已在新版提示模板里加了「工具解锁」说明来缓解）。

---

## 二、排查中发现的 6 个「与文档不符」的事实

这些会直接影响后续排期，请先过一眼：

1. **JSON 结构化输出协议目前完全没生效。**
   `src/agents/common/model/__init__.py` 是**空文件** → `_get_output_schema()` 永远 ImportError → 返回 None → `_validate_output()` 恒判定通过。
   **后果**：子智能体返回的是自由文本，`subagents.yaml` 头部写的「统一输出协议 JSON」是纸面约定；中间件里的重试循环也是死代码。
   **好消息**：这让 4→2 合并不需要同步合并 Output Schema，风险比预想低。

2. **`src/agents/subagents/factory.py` 是死代码。**
   `graph.py` 用的是自己文件内的 `load_subagent()`，从没调用 factory 的 `create_subagent_from_config()`。所以 factory 里的 `schema_map`（researcher/analyst/critic/memory_manager → Output）改不改都不影响运行。

3. **`general_purpose_agent=True` 会多注入第 5 个子智能体。**
   `SubAgentMiddleware(...)` 传了 `general_purpose_agent=True`，会额外挂一个 `general-purpose`，与「收敛到 2 个」的目标**冲突**。要不要关掉，我留给你决定（关掉是好是坏取决于主智能体是否依赖它兜底）。

4. **文档里的工具名与实际不符。**
   - `retrieve_past_decisions` → 实际叫 **`recall_past_decisions`**（已按实际名字写进 YAML）
   - `read_decisions` / `write_decisions` / `write_experience_review` / `query_warranty` → **都还不存在**

5. **`display_name` 的端到端链路未验证。**（见上文 §4 说明）

6. **证据注入机制已失效。**
   `_enrich_task_description()` 按 `analyst` / `critic` 名字做「上游数据注入 task 描述」，人设改名后两个分支都不再命中 → 空转。当前**无副作用**，但如果你想保留「把搜索结果自动塞给下游」的能力，需要重新设计（合并成一个子智能体后，这个能力本身也不再必要）。

---

## 三、还需要你定的 2 件事

1. **`general_purpose_agent` 关不关？**（见上面第 3 点）
2. **要不要顺手把 JSON 输出协议修活？**
   即在 `model/__init__.py` 导出 `PrePurchaseOutput` / `PostPurchaseOutput`（需要按合并后的人设重新设计 schema 形状，属于**设计决策**，所以我没有擅自造）。
   - 不修：维持现状（自由文本），改动最小；
   - 修：主智能体拿到的子智能体结果变成可校验的 JSON，出卡更稳，但要新增两个 schema 并做回归测试。

---

## 四、下一步建议

1. 你 review 改动：`git diff --ignore-cr-at-eol`（8 个已跟踪文件），新增的 `skills/` 与 `src/agents/common/toolkits/skills/` 直接看文件即可。
2. 定完第三节那 2 件事之后，再决定是否部署到 111.229.209.47。
3. 部署后跑一轮真实对话回归，重点看六件事：
   - 主智能体是否还会派发 `researcher` / `analyst` 这类**已不存在**的 subagent_type（会直接报错返回）；
   - 单域需求（如「帮我看看这个手机值不值」）是否会不必要地调度；
   - 前端对话里子智能体显示名是**中文**还是英文 slug（`subagent_name` 链路验证）；
   - **子智能体会不会主动调 `read_skill`**：给一个「帮我对比这两款」的需求，看日志里是否出现 `read_skill(skill="comparing-products")`；
   - **新补的两个技能能否被触发**：给「想买个通勤耳机」（模糊需求）看是否走 `clarifying-needs`；丢一个商品链接问「这个值不值」看是否走 `evaluating-fit`；
   - **工具门控是否生效**：给一个比价需求，看日志里模型是否**先** `read_skill("hunting-deals")`、**再**调 `price_calculator`。若模型在没读技能时就抱怨「没有计算工具」，说明提示里的「工具解锁」说明还需要加强；
   - **技能脚本能否执行**：给「9 月 1 日签收的，现在还能退吗」，看是否调 `run_skill_script("handling-after-sales", "scripts/after_sales_window.py", …)` 并拿到正确天数；
   - **容器内 `/app/skills` 是否可读（含嵌套资源文件）**：`docker compose exec api ls -R /app/skills` 应能看到各 `SKILL.md`；
     **并特别确认嵌套的 `skills/pre_purchase/checking-compatibility/references/category-field-matrix.md` 也在**——
     这是 `.dockerignore` 里 `*.md` 与 `!skills/**` 规则能否覆盖嵌套目录的关键验证点，漏掉会静默失败。
