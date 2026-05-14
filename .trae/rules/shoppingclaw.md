这是一个基于LangGraph的多Agent项目，必须遵循工程化开发规范。

1. 模块优先，禁止混乱开发
所有功能必须拆分为独立模块：
- agent/
- tools/
- graph/
- state/

禁止在一个文件中混合所有逻辑。

2. 明确任务，如果面对用户模糊的需求，直接问问题询问



3. 统一State管理
所有数据流必须通过state传递：
- 不允许使用全局变量
- state结构必须提前定义清晰

例如：
{
  "query": str,
  "docs": list,
  "summary": str,
  "answer": str
}

4. Graph结构清晰
LangGraph流程必须明确：
- 起点（entry）
- 节点（nodes）
- 条件分支（if/else）
- 终点（END）

禁止隐式流程。

5. 每个Node必须可单测
每个节点函数必须：
- 输入state
- 输出state字段
- 可单独运行测试

6. 工具调用规范
tools必须：
- 单一职责
- 独立文件
- 可复用

禁止把工具逻辑写在agent里。

7. Prompt必须结构化
所有prompt必须：
- 明确角色
- 明确任务
- 明确输出格式

禁止随意自然语言prompt。

8. 每次先做一个小功能


禁止一次性写完整系统。

9. 所有代码必须可解释
任何复杂逻辑必须：
- 添加注释
- 能解释数据流

10. 项目目标
该项目不是demo，而是：
- 可展示的GitHub项目
- 具备工程结构
- 可扩展的多Agent系统