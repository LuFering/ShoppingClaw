# Agent 流程可视化改造说明

## 概述

本次改造深度整合了 ScienceClaw 的优秀前端设计，在保持 ShoppingClaw 原有设计风格的基础上，实现了更专业、更直观的 Agent 执行流程可视化。

## 核心改进

### 1. 新增组件体系

#### AgentFlowPanel.vue
- **主流程面板**，替代原有的 ThinkingProcessSidebar
- 采用分层折叠结构（思考过程 → 任务进度 → 工具调用）
- 支持智能自动滚动和状态管理
- 响应式设计，移动端全屏展示

#### StepMessage.vue
- **步骤消息组件**，展示每个执行步骤的状态
- 状态图标动画（旋转/完成/失败）
- 可展开查看关联的工具调用
- 点击选中高亮效果

#### ToolCallCard.vue
- **工具调用卡片**，展示工具执行的详细信息
- 智能参数预览（根据工具类型提取关键参数）
- 耗时徽章显示（绿色渐变）
- 可展开查看完整输入/输出

### 2. 设计亮点

#### 视觉层次
```
┌─────────────────────────────────┐
│ 🔵 思考中...                     │  ← Header: 状态指示器
├─────────────────────────────────┤
│ 💡 思考过程          [3/5]      │  ← Section 1: 推理内容
│   └─ 折叠/展开                   │
├─────────────────────────────────┤
│ 📋 任务进度          [2/4]      │  ← Section 2: 计划步骤
│   ├─ ✅ 搜索产品                │
│   ├─ 🔄 获取详情 (running)      │
│   └─ ⏳ 分析对比                │
├─────────────────────────────────┤
│ 🔧 工具调用          [5]        │  ← Section 3: 工具列表
│   ├─ 🔍 search_products 320ms  │
│   └─ 📋 get_detail    1.2s     │
└─────────────────────────────────┘
```

#### 状态动画
- **运行中**: 蓝色旋转圆环 + 脉冲点
- **已完成**: 绿色渐变勾选图标
- **失败**: 红色警告图标
- **待处理**: 灰色空心圆

#### 交互优化
- 步骤点击筛选关联工具
- 工具卡片悬停阴影提升
- 平滑的展开/折叠过渡
- 自动滚动到最新内容

### 3. 技术实现

#### 数据流
```javascript
// AgentChatComponent.vue 中的数据状态
const thinkingState = reactive({
  isOpen: false,        // 面板开关
  steps: [],            // 思考步骤数组
  planSteps: [],        // 计划步骤数组
  toolCalls: [],        // 工具调用数组
  isInitialRender: true // 初始渲染标记
})

// SSE 事件处理
if (chunk.thinking_step) {
  addThinkingStep(chunk.thinking_step)
}
if (chunk.plan) {
  applyPlanSteps(chunk.plan.steps || [])
}
if (chunk.tool_call) {
  upsertToolCall(chunk.tool_call)
}
```

#### 组件通信
```vue
<!-- AgentChatComponent.vue -->
<AgentFlowPanel
  :is-open="thinkingState.isOpen"
  :thinking-steps="thinkingState.steps"
  :plan-steps="thinkingState.planSteps"
  :tool-calls="thinkingState.toolCalls"
  :is-processing="isProcessing"
  @close="closeThinkingSidebar"
  @step-select="handleStepSelect"
  @tool-click="handleToolClick"
/>
```

## 使用方法

### 切换新旧面板

在 `AgentChatComponent.vue` 中修改配置：

```javascript
// 使用新流程面板 (ScienceClaw 风格)
const useNewFlowPanel = ref(true)  // true: 新面板, false: 旧面板
```

### 自定义样式

全局样式文件位于：
```
web-v2/src/assets/styles/agent-flow.css
```

可自定义的主题变量：
```css
:root {
  --step-pending: #d1d5db;
  --step-running: #3b82f6;
  --step-completed: #10b981;
  --step-failed: #ef4444;
  
  --thinking-bg: rgba(245, 158, 11, 0.05);
  --progress-gradient: linear-gradient(90deg, #3b82f6, #60a5fa);
}
```

### 扩展功能

#### 添加工具元数据
在后端 SSE 事件中返回 `tool_meta`：

```python
{
  "status": "thinking_process",
  "event": "tool_call",
  "tool_call": {
    "name": "search_products",
    "args": {"query": "iPhone 16"},
    "tool_meta": {
      "icon": "🔍",
      "category": "search",
      "description": "搜索商品"
    }
  }
}
```

#### 自定义步骤状态
支持的步骤状态值：
- `pending` - 待处理
- `running` / `in_progress` - 执行中
- `completed` / `done` - 已完成
- `failed` / `error` - 失败

## 性能优化

### 1. 虚拟滚动（未来优化）
当工具调用超过 50 个时，建议启用虚拟滚动：

```javascript
import { useVirtualList } from '@vueuse/core'

const { list, containerProps, wrapperProps } = useVirtualList(
  toolItems,
  { itemHeight: 60 }
)
```

### 2. 防抖处理
思考内容更新时使用防抖：

```javascript
import { debounce } from 'lodash-es'

const updateThinkingContent = debounce((content) => {
  thinkingState.steps.push({ type: 'thinking', content })
}, 100)
```

### 3. 内存管理
组件卸载时清理定时器：

```javascript
onUnmounted(() => {
  // 清理事件监听器、定时器等
})
```

## 兼容性说明

### 浏览器支持
- Chrome 90+
- Firefox 88+
- Safari 14+
- Edge 90+

### 特性检测
```javascript
// CSS backdrop-filter 支持检测
if (!CSS.supports('backdrop-filter', 'blur(12px)')) {
  document.body.classList.add('no-backdrop-filter')
}
```

## 故障排查

### 问题 1: 面板无法打开
**原因**: `thinkingState.isOpen` 未正确设置

**解决**:
```javascript
const toggleThinkingSidebar = () => {
  thinkingState.isOpen = !thinkingState.isOpen
  thinkingState.isInitialRender = false
}
```

### 问题 2: 工具调用不显示
**原因**: SSE 事件中缺少 `tool_call` 字段

**解决**: 检查后端是否正确发送工具调用事件

### 问题 3: 样式冲突
**原因**: 全局样式覆盖

**解决**: 使用 scoped 样式或提高选择器优先级

## 后续优化方向

### Phase 1: 基础增强
- [ ] 添加工具调用统计图表
- [ ] 支持步骤时间线视图
- [ ] 导出执行日志功能

### Phase 2: 高级功能
- [ ] 实时协作编辑（多用户查看同一会话）
- [ ] AI 辅助调试（自动识别异常步骤）
- [ ] 性能分析面板（Token 消耗、响应时间）

### Phase 3: 生态集成
- [ ] VS Code 插件同步
- [ ] Slack/Discord 通知
- [ ] Webhook 回调支持

## 参考资源

- [ScienceClaw Frontend](D:\ScienceClaw\ScienceClaw\frontend)
- [Vue 3 Transition](https://vuejs.org/guide/built-ins/transition.html)
- [Lucide Icons](https://lucide.dev/icons/)
- [Ant Design Vue](https://antdv.com/)

---

**最后更新**: 2026-05-15  
**版本**: v1.0.0  
**作者**: ShoppingClaw Team
