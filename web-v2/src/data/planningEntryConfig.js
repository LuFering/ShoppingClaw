/**
 * 采购规划 · 入口页配置
 *
 * 从 `data/purchaseDemo.js` 拆出来的**可维护数据**（2026-09-24）。
 * 这些不是 mock：预设方案与表单选项是运营/产品会改的配置，
 * 后端接上后照旧由前端提供（它们描述的是「怎么问」，不是「答什么」）。
 */

/** 预设方案：点一张 = 自动填好场景/预算/周期，直接带参数进工作台 */
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

/** 入口页表单选项 */
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
