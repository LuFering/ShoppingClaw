/**
 * 采购决策图 · 视觉语义表
 *
 * 从 `data/purchaseDemo.js` 拆出来的**设计资产**（2026-09-24）：
 * 颜色/线型/状态机是设计决策，不是演示数据 —— 后端接上后它们照旧生效。
 * 原先和 mock 数据混在一个文件里，删 mock 时容易连带删掉这些。
 *
 * 取的色值来自项目已有的 --chart-palette-*，不新增色板。
 * 「决策依据」用中性灰：语义上它是背景知识而非决策对象。
 */

/** 节点类型 → 颜色 */
export const NODE_TYPE_COLOR = {
  核心任务: '#f6bd16',
  需求: '#6dc8ec',
  采购对象: '#5ad8a6',
  候选商品: '#9581cc',
  决策依据: '#8c8c8c',
  预算约束: '#92d050',
  风险: '#f27c7c'
}

/** 核心任务固定占画布中心（radial 布局的 focus），需要单独标记 */
export const CORE_TYPE = '核心任务'

/**
 * 关系 → 线型。
 * dash = true 表示虚线：表达「非确定」的关系（替代/依赖/排除）。
 */
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

/**
 * 生命周期状态 → 视觉。后端产出的节点带 state，界面据此决定
 * 透明度/描边/是否中空。
 *
 *   pending   待探索：中空 + 低透明 —— 用户能预见「它接下来要去找这些」
 *   active    探索中：满血
 *   candidate 通过初筛：正常
 *   selected  采纳：放大 + 绿环
 *   pruned    淘汰：降透明。**注意「不删除」** —— 删掉就成黑箱了
 */
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

/** 状态 → 中文标签（右栏详情条与图例共用） */
export const STATE_LABEL = {
  pending: '待探索',
  active: '探索中',
  candidate: '候选',
  selected: '已采纳',
  pruned: '已排除'
}
