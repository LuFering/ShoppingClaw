/**
 * 采购规划 · 演示数据
 *
 * 现在后端还没有 planning_agent，所以这一层是 mock。
 * 但字段结构刻意与最终契约对齐（见 web-v2/docs/采购智能体界面设计.html），
 * 后端接上后只需把这里换成真实数据源，界面层不用改。
 *
 * 决策图的核心是「随执行收敛」：节点不是一次性给全的，
 * 每个节点带 state，界面按 state 决定透明度/描边/是否中空。
 */

/* ── 决策图：节点类型 → 颜色 ──────────────────────────────
 * 取项目已有的 --chart-palette-* 值，不新增色值。
 * 「决策依据」用中性灰，语义上它是背景知识而非决策对象。 */
export const NODE_TYPE_COLOR = {
  核心任务: '#f6bd16',
  需求: '#6dc8ec',
  采购对象: '#5ad8a6',
  候选商品: '#9581cc',
  决策依据: '#8c8c8c',
  预算约束: '#92d050',
  风险: '#f27c7c'
}

/** 核心任务固定占画布中心，需要单独标记 */
export const CORE_TYPE = '核心任务'

/* ── 决策图：关系 → 线型 ────────────────────────────────
 * dash = true 表示虚线：表示「非确定」的关系（替代/依赖/排除） */
export const RELATION_STYLE = {
  需要: { color: '#6dc8ec', dash: false },
  拆解为: { color: '#5ad8a6', dash: false },
  约束: { color: '#92d050', dash: false },
  候选: { color: '#9581cc', dash: false },
  满足: { color: '#92d050', dash: false },
  依据: { color: '#8c8c8c', dash: false },
  存在: { color: '#f27c7c', dash: false },
  替代: { color: '#8c8c8c', dash: true },
  依赖: { color: '#dca63a', dash: true },
  排除: { color: '#f27c7c', dash: true }
}

/* ── 决策图：生命周期状态 → 视觉 ─────────────────────────
 * pending  待探索：中空 + 低透明，用户能预见「它接下来要去找这些」
 * active   探索中：满血
 * candidate 通过初筛：正常
 * selected 采纳：放大 + 绿环
 * pruned   淘汰：降透明。注意「不删除」—— 删掉就成黑箱了 */
export const NODE_STATE_STYLE = {
  pending: { opacity: 0.42, lineWidth: 1.4, scale: 0.86, hollow: true },
  active: { opacity: 1, lineWidth: 2, scale: 1 },
  candidate: { opacity: 0.94, lineWidth: 1.5, scale: 1 },
  selected: { opacity: 1, lineWidth: 3, scale: 1.18, ring: '#92d050' },
  pruned: { opacity: 0.35, lineWidth: 1, scale: 0.92, muted: true }
}

export const SELECTED_RING = '#92d050'
/** 淘汰节点的填充降饱和，用中性灰替代本色 */
export const PRUNED_FILL = '#4c4d4d'

/* ── 决策图数据：展开后的完整快照 ───────────────────────── */
const ALL_NODES = [
  { id: 'task', name: '本次采购任务', type: '核心任务', importance: 5, state: 'active', meta: { scene: '装修' } },

  { id: 'need-silent', name: '静音好打理', type: '需求', importance: 4, state: 'candidate', meta: {} },
  { id: 'need-budget', name: '预算 ¥5000', type: '需求', importance: 4, state: 'candidate', meta: {} },
  { id: 'need-battery', name: '续航 150㎡', type: '需求', importance: 3, state: 'candidate', meta: {} },
  { id: 'need-elder', name: '有老人同住', type: '需求', importance: 3, state: 'pending', meta: {} },

  { id: 'obj-1', name: '洗地机', type: '采购对象', importance: 5, state: 'candidate', meta: {} },

  { id: 'cand-1', name: '添可芙万 3.0', type: '候选商品', importance: 4, state: 'selected', meta: { price: 2199 } },
  { id: 'cand-2', name: '石头 A30', type: '候选商品', importance: 3, state: 'candidate', meta: { price: 2599 } },
  { id: 'cand-3', name: '追觅 H13', type: '候选商品', importance: 3, state: 'pruned', meta: { price: 2899, pruneReason: '噪音 62dB，不满足「静音」' } },
  { id: 'cand-4', name: '小米 X40', type: '候选商品', importance: 2, state: 'pending', meta: {} },

  { id: 'ev-1', name: '类目知识', type: '决策依据', importance: 3, state: 'candidate', meta: {} },
  { id: 'ev-2', name: '噪音实测', type: '决策依据', importance: 2, state: 'pending', meta: {} },

  { id: 'bud-1', name: '以旧换新券', type: '预算约束', importance: 2, state: 'candidate', meta: {} },

  { id: 'risk-1', name: '耗材成本', type: '风险', importance: 3, state: 'candidate', meta: {} }
]

const ALL_EDGES = [
  { source_id: 'task', target_id: 'need-silent', type: '需要' },
  { source_id: 'task', target_id: 'need-budget', type: '需要' },
  { source_id: 'task', target_id: 'need-battery', type: '需要' },
  { source_id: 'task', target_id: 'need-elder', type: '需要' },
  { source_id: 'task', target_id: 'obj-1', type: '拆解为' },
  { source_id: 'task', target_id: 'bud-1', type: '约束' },

  { source_id: 'obj-1', target_id: 'cand-1', type: '候选' },
  { source_id: 'obj-1', target_id: 'cand-2', type: '候选' },
  { source_id: 'obj-1', target_id: 'cand-3', type: '候选' },
  { source_id: 'obj-1', target_id: 'cand-4', type: '候选' },

  { source_id: 'cand-1', target_id: 'need-silent', type: '满足' },
  { source_id: 'cand-1', target_id: 'need-budget', type: '满足' },
  { source_id: 'cand-1', target_id: 'ev-1', type: '依据' },
  { source_id: 'cand-1', target_id: 'ev-2', type: '依据' },
  { source_id: 'cand-1', target_id: 'risk-1', type: '存在' },

  { source_id: 'cand-2', target_id: 'cand-1', type: '替代' },
  { source_id: 'task', target_id: 'cand-3', type: '排除' }
]

/**
 * 按执行进度切出决策图。
 * progress 0-1：pending 节点按比例逐步「点亮」，模拟 agent 边跑边长图。
 * 这里不真做动画（动效由 G6 的状态过渡承担），只决定可见集合。
 */
export const buildDecisionGraph = (progress = 1) => {
  const p = Math.max(0, Math.min(1, progress))
  const nodes = ALL_NODES.map((n) => {
    if (n.state !== 'pending') return n
    // pending 节点按进度依次转成 candidate；进度满则全部点亮
    const idx = ALL_NODES.filter((x) => x.state === 'pending').findIndex((x) => x.id === n.id)
    const total = ALL_NODES.filter((x) => x.state === 'pending').length || 1
    const lit = p >= 1 || idx < Math.floor(p * total)
    return lit ? { ...n, state: 'candidate' } : n
  })
  return { nodes, edges: ALL_EDGES }
}

export const DECISION_GRAPH_FULL = buildDecisionGraph(1)

export const DECISION_GRAPH_META = {
  totalExpected: ALL_NODES.length,
  scene: '装修',
  subject: '洗地机'
}

/* ── 左栏：agent 执行流 ─────────────────────────────────
 * kind: think 思考 / retrieve 检索 / call 调用 / produce 产出 */
export const EXEC_STREAM = [
  {
    kind: 'think',
    title: '把需求拆成静音、预算、续航三条硬约束',
    state: 'done',
    time: '09:41:02'
  },
  {
    kind: 'retrieve',
    title: '类目知识 · 洗地机选购标准',
    detail: '命中 3 条评估标准',
    state: 'done',
    time: '09:41:05'
  },
  {
    kind: 'call',
    title: '搜索商品 ·「洗地机 静音 自清洁」',
    detail: '返回 11 个 SKU · 1.4s',
    state: 'done',
    time: '09:41:07'
  },
  {
    kind: 'think',
    title: '追觅 H13 实测噪音 62dB，不满足「静音」，排除',
    detail: '已写入决策图的「排除」关系',
    state: 'done',
    time: '09:41:11'
  },
  {
    kind: 'call',
    title: '比价 · 3 款候选横比',
    detail: '正在拉取实时价与券',
    state: 'running',
    time: '09:41:14'
  },
  {
    kind: 'retrieve',
    title: '风评与售后政策 · 添可芙万 3.0',
    detail: '待执行',
    state: 'todo',
    time: ''
  },
  {
    kind: 'produce',
    title: '生成采购方案与预算分配表',
    detail: '待候选收敛',
    state: 'todo',
    time: ''
  }
]

/* ── 右栏：待交付 ─────────────────────────────────────── */
export const DELIVERABLES = [
  {
    id: 'd-plan',
    name: '采购方案.md',
    meta: '7 项 · 3 组 · 总 60,000',
    state: 'ready'
  },
  {
    id: 'd-compare',
    name: '候选对比表',
    meta: '3 款横比 · 等候选收敛',
    state: 'running',
    progress: 0.6
  },
  {
    id: 'd-budget',
    name: '预算分配表',
    meta: '依赖采购方案冻结',
    state: 'waiting'
  }
]

/** agent 停下来等用户拍板的问题，固定显示在右栏而不是混进执行流 */
export const PENDING_QUESTION = {
  text: '预算要不要放宽到 6000？现有候选都逼近 5000 上限。',
  options: [
    { key: 'keep', label: '不放宽', primary: false },
    { key: 'raise', label: '放宽到 6000', primary: true }
  ]
}

/* ── 入口页：预设方案 ───────────────────────────────────
 * 点一张卡 = 自动填好场景/预算/周期，直接带参数进工作台。
 * 它是可维护的数据，不是写死的 UI。 */
export const PRESET_PLANS = [
  {
    id: 'p-reno',
    title: '三居室装修',
    budget: '¥80,000',
    duration: '6 周',
    desc: '6 类约 60 项，含硬装前置与尺寸确认',
    params: { scene: '装修', budget: 80000, duration: '6 周' }
  },
  {
    id: 'p-winter',
    title: '换季 · 冬装',
    budget: '¥3,000',
    duration: '2 周',
    desc: '4 类 8 项，按家庭成员分工',
    params: { scene: '换季', budget: 3000, duration: '2 周' }
  },
  {
    id: 'p-move',
    title: '搬家置办',
    budget: '¥12,000',
    duration: '3 周',
    desc: '5 类 12 项，按入住先后排序',
    params: { scene: '搬家', budget: 12000, duration: '3 周' }
  },
  {
    id: 'p-school',
    title: '开学装备',
    budget: '¥5,000',
    duration: '1 周',
    desc: '3 类 9 项，宿舍尺寸前置',
    params: { scene: '开学', budget: 5000, duration: '1 周' }
  }
]

/* ── 入口页：表单选项 ─────────────────────────────────── */
export const ENTRY_FORM = [
  {
    key: 'scene',
    label: '场景',
    required: true,
    type: 'single',
    options: ['装修', '换季', '搬家', '开学']
  },
  {
    key: 'budget',
    label: '总预算',
    required: true,
    type: 'single',
    options: ['¥3万', '¥6万', '¥8万', '自定义']
  },
  {
    key: 'when',
    label: '什么时候要',
    required: false,
    type: 'single',
    options: ['下月开工', '已开工', '指定日期']
  },
  {
    key: 'constraints',
    label: '硬约束（可多选）',
    required: false,
    type: 'multi',
    options: ['有老人', '要静音', '空间受限', '有宠物']
  }
]
