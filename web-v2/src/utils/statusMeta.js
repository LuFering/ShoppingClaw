/**
 * 事件/状态语义表 —— 全站唯一一份。
 *
 * 为什么抽出来（U5）：这份表原先在三个地方各写一遍 ——
 *   · `AgentChatComponent.vue:326` 的 statusTypeMeta（8 种事件类型，带图标色）
 *   · `AssistantView.vue` 的 hitLabel / resultLabel / doneText（内联三目）
 * 加一种事件类型要改两处，必然会漂。现在统一到这里。
 *
 * 两类键不要混：
 *   · `STATUS_TYPE_META` 的键是**事件类型**（notify_service 产出的 8 种，
 *     见 src/services/notify_service.py 顶部注释），用于首页状态卡。
 *   · `HIT_TYPE_LABEL` 的键是**任务类型**（price/deal/coupon/rank/shop），
 *     用于助理页的命中提醒卡。两者刻意不同：事件流把 rank→price、
 *     shop→coupon 收敛过（因为状态卡只画 8 种），而命中卡有独立的五种语义。
 */
import {
  Brain,
  Heart,
  ShieldAlert,
  Star,
  Tag,
  TrendingDown,
  Wrench,
} from 'lucide-vue-next'

/** 首页状态卡：事件类型 → 文案 / 颜色 / 图标。键与 notify_service 的 type 对齐。 */
export const STATUS_TYPE_META = {
  price: { label: '盯价 · 降价', color: '#d6543f', icon: TrendingDown },
  coupon: { label: '券 · 到期', color: '#b45309', icon: Tag },
  // 2026-09-29：`stock`（补货）已下线 —— 导购 MCP 不提供库存数据。
  // 换成「优惠到期」：活动结束时间是真实且全覆盖的信号。
  deal: { label: '优惠 · 到期', color: '#b45309', icon: Tag },
  decide: { label: '决策 · 待定', color: '#178a67', icon: Brain },
  fav: { label: '收藏 · 动态', color: '#178a67', icon: Star },
  prefer: { label: '偏好 · 确认', color: '#178a67', icon: Heart },
  care: { label: '售后 · 耗材', color: '#185fa5', icon: Wrench },
  review: { label: '风评 · 异动', color: '#b45309', icon: ShieldAlert },
}

/** 未知类型兜底，避免 `meta[type].color` 取到 undefined 把整卡画白。 */
export const FALLBACK_STATUS_META = {
  label: '动态',
  color: '#6b7280',
  icon: Star,
}

export const statusMeta = (type) => STATUS_TYPE_META[type] || FALLBACK_STATUS_META

/** 助理页命中卡：任务类型 → 中文短标签。键是 task_type，不是事件 type。 */
export const HIT_TYPE_LABEL = {
  price: '降价',
  deal: '优惠到期',
  coupon: '优惠券',
  rank: '榜单',
  shop: '店铺活动',
}

/** 执行日志结果 → 五态文案（与 task_api.js 的 mapLastResult 同语义）。 */
export const RESULT_LABEL = {
  hit: '命中',
  ok: '成功',
  empty: '无变化',
  fail: '失败',
  run: '执行中',
}

/** 卡片动作的落地状态文案。 */
export const DONE_TEXT = {
  viewed: '已查看',
  archive: '已转存到购物档案',
  ignored: '已忽略',
  later: '已稍后处理',
}

export const hitLabel = (t) => HIT_TYPE_LABEL[t] || t || '提醒'
export const resultLabel = (r) => RESULT_LABEL[r] || r
export const doneText = (a) => DONE_TEXT[a] || a
