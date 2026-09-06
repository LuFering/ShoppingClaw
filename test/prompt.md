基于项目架构和业务场景文档，我给出**超越聊天界面的前端功能设计**：

---

## 一、核心洞察：聊天界面的局限性

当前 `AgentChatComponent.vue` 是**线性对话流**，但电商决策本质是**多维信息探索**。用户需要：
- 同时对比多个商品（聊天只能串行展示）
- 快速筛选维度（聊天需要反复追问）
- 可视化数据趋势（文字描述不如图表直观）
- 持久化收藏管理（聊天记录难以回溯）

---

## 二、新增前端模块（按价值排序）

### **1. 智能对比工作台（最高优先级）**

#### 设计理念
将"推荐-对比-决策"从对话中剥离，形成独立的工作空间。

#### UI 布局
```
┌─────────────────────────────────────────────────────┐
│  顶部工具栏                                          │
│  [添加商品] [清空] [导出PDF] [分享链接]              │
├──────────┬──────────┬──────────┬────────────────────┤
│          │          │          │                    │
│  商品A   │  商品B   │  商品C   │  维度评分雷达图     │
│  iPhone  │  小米14  │  OPPO    │  (ECharts)         │
│  ¥7999   │  ¥4999   │  ¥3999   │                    │
│          │          │          │                    │
├──────────┼──────────┼──────────┤                    │
│ ✅ 性能95│ ✅ 性能88│ ⚠️ 性能75│  性能: A>B>C       │
│ ✅ 拍照90│ ⚠️ 拍照85│ ❌ 拍照70│  拍照: A>B>C       │
│ ⚠️ 续航80│ ✅ 续航90│ ✅ 续航85│  续航: B>C>A       │
│ ❌ 价格高│ ✅ 性价比高│✅ 性价比极高│                  │
├──────────┴──────────┴──────────┴────────────────────┤
│  底部结论区（由 Analyst Agent 生成）                  │
│  "预算充足选A，追求性价比选C，均衡选B"                │
└─────────────────────────────────────────────────────┘
```


#### 技术实现
**数据结构（后端返回）：**
```python
# src/agents/subagents/factory.py - AnalysisAgent 输出
{
  "comparison_table": [
    {
      "sku_id": "100012345",
      "name": "iPhone 15 Pro",
      "price": 7999,
      "image_url": "...",
      "scores": {
        "performance": {"value": 95, "evidence": "A17 Pro芯片，Geekbench单核2900"},
        "camera": {"value": 90, "evidence": "4800万主摄，ProRAW格式"},
        "battery": {"value": 80, "evidence": "3274mAh，重度使用6小时"}
      },
      "risks": ["价格偏高", "充电速度慢"]
    }
  ],
  "recommendation_summary": "..."
}
```


**前端组件：**
- `ComparisonWorkspace.vue` - 主容器
- `ProductColumn.vue` - 单商品列（可拖拽排序）
- `DimensionRadar.vue` - 多维度雷达图
- `VerdictPanel.vue` - 结论面板

**交互逻辑：**
1. 用户在聊天中说"对比这三款手机"
2. MasterAgent 调用 ResearchAgent 获取商品数据
3. AnalysisAgent 生成对比表格 JSON
4. 前端自动切换到对比工作台视图
5. 用户可手动添加/删除商品列

---

### **2. 决策看板（Dashboard）**

#### 设计理念
将分散的购物决策过程**可视化沉淀**，形成个人消费知识图谱。

#### 模块划分

##### 2.1 偏好画像面板
**数据来源：** MemoryManager + UserProfile

**UI 展示：**
```
┌─────────────────────────────────┐
│  📊 我的购物画像                 │
├─────────────────────────────────┤
│  品牌偏好：                      │
│  ████████░░ 小米 (80%)         │
│  ██████░░░░ 华为 (60%)         │
│  ████░░░░░░ OPPO (40%)         │
│                                 │
│  价格敏感度：中高                │
│  常购品类：数码 > 家电 > 服饰    │
│  决策风格：参数党（看重性能）     │
│                                 │
│  [编辑偏好] [查看历史决策]       │
└─────────────────────────────────┘
```


**技术实现：**
```javascript
// stores/userProfile.js
export const useUserProfileStore = defineStore('userProfile', {
  state: () => ({
    brand_scores: {},  // 品牌偏好分数
    price_sensitivity: 0.7,  // 0-1，越高越敏感
    decision_style: 'parameter_focused',  // 决策风格标签
    category_distribution: { '数码': 0.6, '家电': 0.3 }
  }),
  actions: {
    async updateFromMemory() {
      const profile = await memoryApi.getProfile(userId)
      this.brand_scores = profile.preferences.brand_preference
      // ...
    }
  }
})
```


##### 2.2 历史决策时间线
**功能：** 回顾过去的购物建议及后续反馈

**UI 设计：**
```
2024-01-15  推荐：小米14 Pro
            用户选择：✅ 购买
            30天后反馈：⭐⭐⭐⭐⭐ "续航超预期"
            
2024-02-20  推荐：Sony WH-1000XM5
            用户选择：❌ 未购买（选了Bose）
            系统学习：用户对降噪要求高于音质
```


**数据流：**
1. 用户购买后主动反馈（或系统追踪订单状态）
2. MemoryManager 更新偏好权重
3. 前端渲染时间线组件 `DecisionTimeline.vue`

##### 2.3 降价监控中心
**功能：** 追踪感兴趣商品的价格波动

**UI 布局：**
```
┌──────────────────────────────────────────┐
│  🔔 降价提醒 (3个)                        │
├──────────────────────────────────────────┤
│  iPhone 15 Pro                           │
│  当前: ¥7999  目标: ¥7500  ↓6.2%        │
│  [取消提醒] [查看详情]                    │
│                                          │
│  小米14 Ultra                            │
│  当前: ¥5999  目标: ¥5500  ↓8.3%        │
│  [取消提醒] [查看详情]                    │
└──────────────────────────────────────────┘
```


**技术实现：**
- 后端定时任务每5分钟检查价格（京东API）
- WebSocket 推送降价通知
- 前端 `NotificationBell.vue` 显示红点

---

### **3. 场景化决策向导（Wizard）**

#### 设计理念
针对复杂决策（如"配电脑"、"装修家电"），提供**结构化引导流程**，而非开放式对话。

#### 交互流程示例：配置游戏电脑

**Step 1: 预算设定**
```
┌─────────────────────────────┐
│  您的总预算是多少？           │
│                             │
│  ○ 5000以下                 │
│  ● 5000-8000  ← 选中        │
│  ○ 8000-12000               │
│  ○ 12000以上                │
│                             │
│  [下一步 →]                 │
└─────────────────────────────┘
```


**Step 2: 用途权重**
```
┌─────────────────────────────┐
│  主要用途（拖动滑块调整权重）  │
│                             │
│  3A游戏    ████████░░ 80%   │
│  视频剪辑  ████░░░░░░ 40%   │
│  日常办公  ██░░░░░░░░ 20%   │
│                             │
│  [← 上一步] [下一步 →]      │
└─────────────────────────────┘
```


**Step 3: 品牌偏好**
```
┌─────────────────────────────┐
│  是否有偏好的品牌？           │
│                             │
│  ☑ NVIDIA显卡               │
│  ☑ Intel CPU                │
│  □ AMD (不偏好)             │
│                             │
│  [← 上一步] [生成方案 →]    │
└─────────────────────────────┘
```


**Step 4: 方案展示**
```
┌─────────────────────────────────────────┐
│  💡 推荐配置方案                         │
├─────────────────────────────────────────┤
│  CPU:    Intel i5-13600K  ¥2299        │
│  GPU:    RTX 4070 Super   ¥4899        │
│  内存:   32GB DDR5        ¥799         │
│  硬盘:   1TB NVMe SSD     ¥499         │
│  总计:   ¥8496 (超预算6%)               │
│                                         │
│  [调整配置] [查看备选方案] [保存方案]   │
└─────────────────────────────────────────┘
```


#### 技术实现
**前端组件：**
- `DecisionWizard.vue` - 向导容器（管理步骤状态）
- `BudgetSelector.vue` - 预算选择器
- `WeightSlider.vue` - 权重滑块组
- `ConfigScheme.vue` - 配置方案展示

**后端支持：**
```python
# src/agents/subagents/factory.py - ResearchAgent 扩展
class ConfigRecommendationTool(BaseTool):
    """根据约束条件生成配置方案"""
    
    async def run(self, budget_range, usage_weights, brand_prefs):
        # 1. 查询兼容的硬件组合
        # 2. 计算性价比得分
        # 3. 返回Top3方案
        return {
            "schemes": [
                {
                    "components": [...],
                    "total_price": 8496,
                    "performance_score": 92,
                    "compatibility_check": "pass"
                }
            ]
        }
```


---

### **4. 实时协作空间（未来形态）**

#### 设计理念
购物决策常需多人参与（情侣选家电、家庭装修），支持**多人实时协作**。

#### 功能设计

##### 4.1 共享决策房间
```
房间ID: SHOP-2024-0115
参与者: 张三(主人), 李四(邀请)

┌──────────────────────────────────────┐
│  当前讨论：客厅电视选购               │
│                                      │
│  张三: "我觉得OLED画质更好"           │
│  李四: "但Mini-LED更耐用吧？"        │
│                                      │
│  [AI助手]: "根据你们的使用场景..."    │
└──────────────────────────────────────┘
```


**技术实现：**
- WebSocket 实时同步消息
- CRDT 算法处理冲突（类似 Figma）
- 权限管理（主人可邀请/移除成员）

##### 4.2 投票决策机制
```
┌─────────────────────────────────┐
│  投票：选择哪款电视？             │
├─────────────────────────────────┤
│  Sony A95L  ██████████ 6票     │
│  Samsung S95C ████ 2票         │
│  LG C3      ██ 1票             │
│                                 │
│  [我要投票] [查看对比详情]      │
└─────────────────────────────────┘
```


---

### **5. AR/3D 预览（前瞻性）**

#### 设计理念
解决"买回来不合适"的痛点，通过增强现实预览效果。

#### 应用场景

**场景1：家具摆放预览**
- 用户上传客厅照片
- AI 识别空间尺寸
- 叠加推荐沙发的3D模型
- 调整角度/颜色实时预览

**场景2：穿搭虚拟试穿**
- 上传全身照
- AI 生成穿着推荐服装的效果
- 支持切换颜色/尺码

**技术栈：**
- Three.js（3D渲染）
- MediaPipe（姿态识别）
- Stable Diffusion（图像生成）

**注意：** 此功能需大量前端优化，属于长期规划。

---

## 三、架构升级建议

### 3.1 路由重构
```javascript
// router/index.js 新增路由
{
  path: '/workspace',
  name: 'Workspace',
  component: AppLayout,
  children: [
    {
      path: 'comparison',
      name: 'ComparisonWorkspace',
      component: () => import('@/views/ComparisonView.vue')
    },
    {
      path: 'dashboard',
      name: 'Dashboard',
      component: () => import('@/views/DashboardView.vue')
    },
    {
      path: 'wizard/:scenario',
      name: 'DecisionWizard',
      component: () => import('@/views/WizardView.vue')
    }
  ]
}
```


### 3.2 全局状态管理
```javascript
// stores/workspace.js
export const useWorkspaceStore = defineStore('workspace', {
  state: () => ({
    activeView: 'chat',  // 'chat' | 'comparison' | 'dashboard'
    comparisonItems: [],
    wizardProgress: {}
  }),
  actions: {
    switchToComparison(products) {
      this.comparisonItems = products
      this.activeView = 'comparison'
    }
  }
})
```


### 3.3 组件通信优化
**问题：** 当前 `AgentChatComponent` 与其他视图隔离

**方案：** 使用 Pinia Store 作为中央状态总线
```javascript
// 聊天组件中
const workspaceStore = useWorkspaceStore()
const handleProductSelect = (product) => {
  workspaceStore.addToComparison(product)
}

// 对比工作台中
const products = computed(() => workspaceStore.comparisonItems)
```


---

## 四、实施优先级矩阵

| 功能模块 | 开发难度 | 用户价值 | 依赖后端 | 优先级 |
|---------|---------|---------|---------|--------|
| 对比工作台 | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | AnalysisAgent | **P0** |
| 决策看板 | ⭐⭐ | ⭐⭐⭐⭐ | MemoryManager | **P0** |
| 场景向导 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ResearchAgent扩展 | P1 |
| 降价监控 | ⭐⭐ | ⭐⭐⭐ | 定时任务+WebSocket | P1 |
| 协作空间 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | WebSocket服务 | P2 |
| AR预览 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 图像处理服务 | P3 |

---

## 五、立即可执行的 TODOLIST

### Week 1: 对比工作台 MVP
1. 创建 `ComparisonWorkspace.vue` 基础布局
2. 实现 `ProductColumn.vue` 商品列组件
3. 集成 ECharts 绘制雷达图
4. 对接 AnalysisAgent 的对比接口

### Week 2: 决策看板
5. 创建 `DashboardView.vue` 主页面
6. 实现偏好画像可视化（品牌柱状图）
7. 开发历史决策时间线组件
8. 对接 MemoryManager 获取用户画像

### Week 3: 降价监控
9. 创建 `PriceAlertBell.vue` 通知组件
10. 实现 WebSocket 连接管理
11. 开发降价列表页面
12. 后端添加价格轮询任务

---

## 六、关键设计原则

1. **聊天不是唯一入口**：复杂决策需要专用工作空间
2. **数据可视化优于文字**：价格趋势、评分对比用图表
3. **持久化胜过 transient**：收藏、监控、历史记录要独立存储
4. **主动引导胜过被动问答**：场景化向导降低认知负担
5. **协作是未来方向**：购物决策常需多人参与

这个方案的核心是**将 AI 能力从"对话式交互"升级为"工作流赋能"**，让前端成为真正的决策辅助平台，而非简单的聊天窗口。