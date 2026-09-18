/**
 * 代购送礼 · v6 三栏工作台数据
 *
 * ⚠️ 与旧的 giftDemo.js 完全无关 —— 旧内容模型（概念卡 / 三件商品 / 替换候选）
 * 在 /proxy 这一版里全部不用。旧页面的数据仍在 giftDemo.js，只服务 /proxy/box 与 /proxy/scroll。
 *
 * 三栏各自的取数：
 *   左栏 礼物探索流  → ACTIONS（7 步，含状态与关键依据）
 *   中栏 人物档案卡  → PROFILE_GROUPS（5 组）+ UNDERSTANDING（当前理解）
 *   右栏 交付区      → DELIVERABLES（6 项，逐步生成）
 *
 * 中栏的三态是硬要求（见用户规格）：
 *   confirmed 已确认（实心点）/ inferred 智能推测（空心圈）/ pending 待确认（灰虚线圈）
 */

export const TASK = {
  recipient: '妈妈',
  occasion: '生日',
  budget: 800
}

/** 中栏 · 档案卡的抬头 */
export const PROFILE_HEAD = {
  name: '妈妈',
  initial: '妈',
  meta: '母亲 · 52 岁',
  sub: '与你同城，周末常见面 · 上次送礼在 3 个月前',
  /** 顶部小徽标：档案完整度 */
  completeness: '档案完整 4/5'
}

/**
 * 中栏 · 五组信息卡。
 * state 三态；danger=true 的组用危险色（禁忌类）；
 * note 是紧随正文的补充说明（淡色）。
 */
export const PROFILE_GROUPS = [
  {
    key: 'relation',
    label: '关系与称谓',
    icon: 'people',
    text: '母亲 · 52 岁 · 与你同城，周末常见面',
    state: 'confirmed',
    source: '购物档案 · 上次送礼记录'
  },
  {
    key: 'life',
    label: '生活状态',
    icon: 'life',
    text: '久坐多；最近提过睡不好',
    note: '（无明显依据）',
    state: 'inferred',
    source: '近 3 次对话提及'
  },
  {
    key: 'likes',
    label: '已知喜好',
    icon: 'heart',
    text: '实用小家电 · 护手霜 · 木质香调',
    state: 'confirmed',
    source: '历史礼物回访 + 明确表达'
  },
  {
    key: 'taboo',
    label: '明确禁忌',
    icon: 'ban',
    text: '香水（过敏）',
    note: '—— 香薰类一律走低烟或无火路线',
    state: 'confirmed',
    danger: true,
    source: '明确表达 · 高置信'
  },
  {
    key: 'giftpref',
    label: '送礼偏好',
    icon: 'gift',
    text: '不喜欢太贵 · 偏好能天天用到的',
    state: 'pending',
    source: '待你确认'
  }
]

/** 中栏 · 底部「当前理解」 */
export const UNDERSTANDING = {
  text: '她在意东西能不能真的用上，而不是贵不贵 —— 所以这一盒要落在「每天都会碰到」上。',
  from: '来自左栏第 2 步「提取需求」'
}

/**
 * 左栏 · 礼物探索流：7 步固定时序。
 * evidence = 关键依据（每步一行，必填 —— 这是「可核对」的落点）
 */
export const ACTIONS = [
  {
    key: 'understand',
    label: '理解关系',
    evidence: '档案里取到「母亲 · 52 岁 · 同城」，并读到禁忌：香水过敏',
    detail: '从档案里只取与本次送礼相关的字段，其余全部过滤掉；把「过敏」标为高置信红线。'
  },
  {
    key: 'extract',
    label: '提取需求',
    evidence: '由「不喜欢太贵 + 要能天天用」推出硬指标：日常使用频次',
    detail: '把两条偏好翻译成一个可筛选的指标，后面的检索与排除都以它为准。'
  },
  {
    key: 'search',
    label: '检索商品',
    evidence: '两组互补关键词，命中 14 件',
    detail: '关键词不是「礼物」，而是「久坐 · 睡眠 · 日常使用」这组场景词。'
  },
  {
    key: 'verify',
    label: '比价验货',
    evidence: '剔除 3 件价格虚高、1 件疑似非正品',
    detail: '比价不看标价看成交价分布；验货看店铺资质与差评关键词。'
  },
  {
    key: 'exclude',
    label: '排除候选',
    evidence: '排除 4 件，理由已留档',
    detail: '被排除的不删除、不隐藏 —— 否则无法回答「为什么最后只剩 3 件」。'
  },
  {
    key: 'combine',
    label: '组合礼盒',
    evidence: '三件落在同一使用场景：每天在家那几小时',
    detail: '单件最优不等于组合最优；这里的判断标准是「同时被用到」。'
  },
  {
    key: 'message',
    label: '生成寄语',
    evidence: '素材＝前面每一步的判断，不是通用祝福',
    detail: '寄语里的每一句都能指回上面某一步的依据。'
  }
]

/** 左栏被排除的候选（保留理由） */
export const EXCLUDED = [
  { name: '香薰精油礼盒', why: '含香精，与「香水过敏」冲突' },
  { name: '高价按摩椅垫', why: '单价超预算一半，违反「不喜欢太贵」' },
  { name: '颈部按摩仪（同款）', why: '上次已送过，重复' },
  { name: '进口助眠软糖', why: '无中文标识，验货未通过' }
]

/** 右栏 · 六类交付物 */
export const DELIVERABLES = [
  { key: 'plan', label: '礼盒方案' },
  { key: 'compare', label: '候选对比' },
  { key: 'budget', label: '预算分配' },
  { key: 'message', label: '寄语文案' },
  { key: 'supply', label: '货源与配送' },
  { key: 'order', label: '送礼订单' }
]

/* ── 交付物的内容（mock，接后端后由流下发） ── */

export const PLAN = {
  title: '让她晚上好过一点',
  thesis: '三件都落在「每天在家那几小时」：一件管睡前、一件管白天坐着、一件写在里面。',
  items: [
    { role: '睡前', name: '无火香薰藤条（木质调）', price: 258, why: '绕开香水过敏；不用点火，卧室更安全' },
    { role: '日常', name: '暖手宝 + 护手霜组合', price: 246, why: '久坐手冷，且护手霜是她一直用的那类' },
    { role: '留言', name: '手写卡片 + 素面礼盒', price: 118, why: '这盒东西唯一的「解释」' }
  ]
}

export const COMPARE = [
  { name: '无火香薰藤条', price: 258, fit: 9, use: '睡前', tag: '入选' },
  { name: '暖手宝 + 护手霜', price: 246, fit: 8, use: '白天', tag: '入选' },
  { name: '手写卡片 + 礼盒', price: 118, fit: 9, use: '拆盒', tag: '入选' },
  { name: '香薰精油礼盒', price: 320, fit: 2, use: '—', tag: '排除' },
  { name: '高价按摩椅垫', price: 468, fit: 4, use: '—', tag: '排除' }
]

export const BUDGET_ROWS = [
  { label: '睡前一件', value: 258 },
  { label: '日常两件', value: 246 },
  { label: '卡片与礼盒', value: 118 }
]

export const MESSAGE = {
  tone: '真诚',
  text: '妈：\n\n我知道你不喜欢我乱花钱。这三样都不贵，但都是我挑了很久、你每天都会碰到的。\n\n藤条不用点火，放在床头就行；手冷了有个小东西揣着；剩下这句，我写在卡片上。\n\n生日不用做什么，就多睡一会儿。'
}

export const SUPPLY = [
  { item: '无火香薰藤条', from: '品牌官方店', eta: '9 月 19 日', note: '当天发' },
  { item: '暖手宝 + 护手霜', from: '平台自营', eta: '9 月 19 日', note: '次日达' },
  { item: '手写卡片 + 礼盒', from: '本地手作', eta: '9 月 20 日', note: '同城当日' }
]

export const ORDER = {
  total: 622,
  budget: 800,
  eta: '9 月 20 日全部到齐',
  steps: ['确认方案', '确认寄语', '下单', '配送到此地址']
}
