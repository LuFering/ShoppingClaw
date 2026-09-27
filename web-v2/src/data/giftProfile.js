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

/**
 * 中栏 · 档案卡的抬头 —— **空壳**。
 *
 * 原先写死「妈妈 / 母亲 · 52 岁 / 与你同城，周末常见面 / 档案完整 4/5」，
 * 同样是编的：后端其实用 `build_profile_head` 按真实已确认组数算完整度
 *（见 gift/stages.py）。这里只留一个兜底形状，真实值一到就覆盖。
 */
export const PROFILE_HEAD = null

/**
 * 中栏 · 五组的**空槽**（骨架）。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-27：这里原本是**硬编码的演示内容**
 * ═══════════════════════════════════════════════════════════════════
 * 原先五组写死了「母亲 · 52 岁 · 与你同城，周末常见面」「香水（过敏）」
 * 这类具体文案。后果是：推演刚开始、后端一个字节都还没返回时，中栏
 * 就已经有字了 —— 看起来是「早就填好的档案」，而不是「正在长出来的
 * 档案」。而且那些文案是**编的**，与项目一贯的零幻觉红线冲突
 *（见 gift/stages.py 的 read_recipient_context）。
 *
 * 现在只保留**结构**（key / label / icon 是前后端约定的固定 schema），
 * 正文留空、state 标 'todo'。前端据此渲染成「空槽」：
 *   · 与后端的 pending（读到了但确实没有）**区分开**
 *   · 数据到了才点亮，这才是真实的生长
 *
 * state 取值（前端 + 后端共用）：
 *   todo      还没读到 —— 空槽，淡虚线
 *   confirmed 已确认 —— 实心点
 *   inferred  智能推测 —— 空心圈
 *   pending   待确认 / 暂时没有 —— 灰虚线圈
 */
/**
 * 中栏 · **建议栏名**的展示元数据。
 *
 * ═══════════════════════════════════════════════════════════════════
 * 2026-09-28：这里原本是 PROFILE_GROUPS —— 五个**预置空槽**
 * ═══════════════════════════════════════════════════════════════════
 * 旧结构是「固定五组、每组一条」，后果（实测）：五组档案全在 run 的
 * 第 8~12 条事件里写满（全程 **7%**），剩下 93% 一条都不写。
 * 用户反馈：「执行流一开始就写完了近半的档案，然后后续思考时多以调用
 * 为主，导致需要较长时间才能输入」。
 *
 * 现在档案是**开放式条目列表**（每条 {id, rail, text, because, source}），
 * 由 agent 每执行一步用 write_profile 写入，可增可改可删。
 * 栏名是开放集合 —— 下面这张表只是**查图标**用的：
 * 命中已知栏名给专属图标，自建栏名走兜底图标。
 *
 * ⚠️ 栏名也**刻意换了一套**（用户明确否决了旧五组：
 *    「不能是这几个，因为之前的测试就是这几个，结果效果不佳」）。
 * 选这组的判据是「每栏的数据来自不同步骤」—— 这是生长能分步发生的原因：
 *   人物信息 ← 入口  送礼往来 ← 读历史  在意什么 ← 读偏好
 *   行情锚点 ← 检索  这盒的取舍 ← 比价  这盒怎么搭 ← 组合
 */
export const RAIL_META = {
  人物信息: { key: 'person', icon: 'people' },
  送礼往来: { key: 'history', icon: 'gift' },
  在意什么: { key: 'cares', icon: 'heart' },
  行情锚点: { key: 'market', icon: 'search' },
  这盒的取舍: { key: 'triage', icon: 'minus' },
  这盒怎么搭: { key: 'pairing', icon: 'link' }
}

/** 自建栏名的兜底图标 —— 不编一个不存在的专属图标 */
export const RAIL_ICON_FALLBACK = 'dot'

/**
 * 「禁忌」类栏名 → 危险区渲染的判据。
 * 从**栏名文字**判断而不是查死表：模型自建「海鲜过敏」这类栏时也该进
 * 危险区，否则最要命的信息会被当普通条目渲染。
 */
const DANGER_HINTS = ['禁忌', '忌讳', '不能', '过敏']

export const isDangerRail = (rail) =>
  DANGER_HINTS.some((h) => String(rail || '').includes(h))

/** 栏名 → {key, icon}，自建栏返回兜底 */
export const railMeta = (rail) =>
  RAIL_META[rail] || { key: `x-${rail || 'misc'}`, icon: RAIL_ICON_FALLBACK }

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
    detail: '从档案里只取与本次送礼相关的字段，其余全部过滤掉；把「过敏」标为高置信红线。'
  },
  {
    key: 'search',
    label: '检索商品',
    detail: '关键词不是「礼物」，而是「久坐 · 睡眠 · 日常使用」这组场景词。'
  },
  {
    key: 'verify',
    label: '比价验货',
    detail: '比价不看标价看成交价分布；验货看店铺资质与差评关键词。'
  },
  {
    key: 'combine',
    label: '组合礼盒',
    detail: '单件最优不等于组合最优；这里的判断标准是「同时被用到」。'
  },
  {
    key: 'message',
    label: '生成寄语',
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
