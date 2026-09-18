/**
 * 代购送礼 · 演示数据
 *
 * 后端还没有 proxy_agent，这一层是 mock；字段结构按最终契约设计，
 * 接上真实数据源后界面层不用改。
 *
 * 三条已确认的设计口径：
 *   1. 素材走「零图片依赖」：氛围用色板+几何构成，包装用 CSS 图案，字体用现有三套
 *   2. 元素替换只允许同类目内（replaceOptions 显式给候选，不做自由替换）
 *   3. 收礼人档案不由用户维护，由阶段 5 的清单落库后自动沉淀
 *
 * ⚠️ 概念的 total 一律由 elements 求和得出（见 `totalOf`），不要手写。
 * 之前手写过一次，结果是概念卡写 ¥680、清单算出 ¥296，两处对不上。
 * 所有概念都必须有 elements —— 否则用户点进去会看到空卡片。
 */

/* ── 情境色板 ────────────────────────────────────────────
 * 每个概念一套 3 色，同时用于氛围构成、缩略图与包装纸。 */
export const PALETTES = {
  moon: ['#c9983c', '#dfc183', '#3a2f26'],   // 晚安治愈集：暖金 + 米 + 深褐
  hand: ['#92d050', '#ead5a8', '#2b3026'],   // 手作温度盒：苔绿 + 米白 + 墨绿
  experience: ['#d85a30', '#f0997b', '#33241f'], // 一起去做的事：陶土红 + 沙 + 深棕
  scent: ['#9581cc', '#c6e6d9', '#2e2108'],  // 气味记忆盒
  warmwinter: ['#d4ac5f', '#ead5a8', '#33241f'], // 过冬保暖组
  desk: ['#5ad8a6', '#ead5a8', '#2b3026']    // 工位治愈角
}

/** 总价唯一来源：元素价格求和。缺元素时才回退到显式 total。 */
export const totalOf = (concept) => {
  const els = concept?.elements || []
  if (!els.length) return Number(concept?.total) || 0
  return els.reduce((s, e) => s + (Number(e.price) || 0), 0)
}

/* ── 阶段 2：概念提案卡 ───────────────────────────────────
 * 卡片之间是「方向差异」，不是同一方向的三个价位。
 * 每张卡必含四样：氛围（palette）· 概念解释（thesis）· 构成（elements）· 总价（由元素算出） */
export const CONCEPTS = [
  {
    id: 'c-moon',
    title: '晚安治愈集',
    thesis: '让她睡得更沉一点。三件都围绕「睡前半小时」搭配，是会每天用到、不会闲置的东西。',
    palette: PALETTES.moon,
    moodLabel: '暖金 · 安静',
    budgetNote: '低于预算 ¥126',
    elements: [
      {
        id: 'el-candle',
        role: '香薰蜡烛',
        name: '雪松佛手柑香薰蜡烛',
        note: '烧 40 小时。放在床头，不用点火也有味道。',
        price: 358,
        status: 'original',
        replaceOptions: [
          { id: 'o-candle-1', name: '无火香薰藤条', note: '不用点火，有小孩或宠物更省心。', price: 398 },
          { id: 'o-candle-2', name: '大豆蜡睡前蜡烛', note: '烟更少，卧室更合适。', price: 298 }
        ]
      },
      {
        id: 'el-tea',
        role: '安睡茶饮',
        name: '洋甘菊薰衣草安睡茶',
        note: '睡前一杯。无咖啡因，不会越喝越醒。',
        price: 198,
        status: 'original',
        replaceOptions: [
          { id: 'o-tea-1', name: '陶瓷带盖马克杯', note: '热牛奶、茶、咖啡都能用，比茶包更不容易闲置。', price: 198 },
          { id: 'o-tea-2', name: '低糖热可可粉', note: '不爱喝茶也能喝，冬天更贴。', price: 178 }
        ]
      },
      {
        id: 'el-card',
        role: '手写卡片',
        name: '手写寄语卡 + 定制礼盒',
        note: '我帮你写，也可以自己改。礼盒和包装一起配好。',
        price: 118,
        status: 'original',
        fixed: true // 卡片与礼盒是概念的锚点，不参与替换
      }
    ]
  },
  {
    id: 'c-hand',
    title: '手作温度盒',
    thesis: '看得出是人挑的、不是下单的。重点在「被认真对待」这四个字。',
    palette: PALETTES.hand,
    moodLabel: '苔绿 · 有手工痕迹',
    budgetNote: '低于预算 ¥186',
    elements: [
      {
        id: 'el-soap',
        role: '手工皂',
        name: '冷制橄榄手工皂',
        note: '带天然纹理，每块都不一样。',
        price: 228,
        status: 'original',
        replaceOptions: [
          { id: 'o-soap-1', name: '乳木果护手霜', note: '更日常，冬天用到概率更高。', price: 248 }
        ]
      },
      {
        id: 'el-felt',
        role: '羊毛毡小物',
        name: '羊毛毡小挂件',
        note: '手工痕迹明显，可以挂在包上。',
        price: 268,
        status: 'original',
        replaceOptions: [
          { id: 'o-felt-1', name: '手作陶瓷小摆件', note: '放桌面上，每天都能看到。', price: 298 }
        ]
      },
      {
        id: 'el-card2',
        role: '手写卡片',
        name: '手写寄语卡 + 干花',
        note: '附一小束干花，拆盒时有气味。',
        price: 118,
        status: 'original',
        fixed: true
      }
    ]
  },
  {
    id: 'c-exp',
    title: '一起去做的事',
    thesis: '不给东西，给一次安排好的共同经历。适合她什么都不缺、但想要你花时间的情况。',
    palette: PALETTES.experience,
    moodLabel: '陶土红 · 一起',
    budgetNote: '接近预算上限',
    elements: [
      {
        id: 'el-class',
        role: '双人体验',
        name: '陶艺体验双人课',
        note: '两小时，成品可以带走。需要提前一周预约。',
        price: 560,
        status: 'original',
        replaceOptions: [
          { id: 'o-class-1', name: '双人料理课', note: '当天就能吃到成果，更热闹。', price: 680 }
        ]
      },
      {
        id: 'el-photo',
        role: '记录',
        name: '拍立得 + 相册',
        note: '当天拍完就能贴进去，比手机照片更像礼物。',
        price: 200,
        status: 'original',
        replaceOptions: [
          { id: 'o-photo-1', name: '定制相框', note: '事后冲印一张放起来，能摆很久。', price: 168 }
        ]
      },
      {
        id: 'el-card3',
        role: '邀请卡',
        name: '手写邀请卡',
        note: '把当天的安排写成一张卡，先给卡再给体验。',
        price: 0,
        status: 'original',
        fixed: true
      }
    ]
  }
]

/** 「换一批灵感」的备选池。
 *  每个都必须有 elements —— 否则用户点进去是空卡片，等于死路。 */
export const CONCEPT_ALTERNATES = [
  {
    id: 'c-scent',
    title: '气味记忆盒',
    thesis: '用气味标记这段时间。适合你们有共同记忆的场景。',
    palette: PALETTES.scent,
    moodLabel: '紫灰 · 记忆',
    budgetNote: '低于预算 ¥196',
    elements: [
      { id: 'al-s1', role: '扩香', name: '香薰扩香石', note: '不用点火，滴几滴精油就行。', price: 258, status: 'original', fixed: true },
      { id: 'al-s2', role: '蜡烛', name: '香氛蜡烛', note: '同一个气味的延续，点起来更像一套。', price: 228, status: 'original', fixed: true },
      { id: 'al-s3', role: '手写卡片', name: '手写寄语卡 + 礼盒', note: '把这段记忆写进去。', price: 118, status: 'original', fixed: true }
    ]
  },
  {
    id: 'c-warm',
    title: '过冬保暖组',
    thesis: '不提浪漫，只管她冷不冷。冬天送最实在。',
    palette: PALETTES.warmwinter,
    moodLabel: '米金 · 暖和',
    budgetNote: '低于预算 ¥136',
    elements: [
      { id: 'al-w1', role: '围巾', name: '羊绒混纺围巾', note: '不扎脖子，颜色好配衣服。', price: 398, status: 'original', fixed: true },
      { id: 'al-w2', role: '手套', name: '加厚触屏手套', note: '不用摘就能看手机，通勤实用。', price: 168, status: 'original', fixed: true },
      { id: 'al-w3', role: '暖手宝', name: '充电暖手宝', note: '办公室和路上都能用。', price: 98, status: 'original', fixed: true }
    ]
  },
  {
    id: 'c-desk',
    title: '工位治愈角',
    thesis: '让她在公司也有个自己的小角落。',
    palette: PALETTES.desk,
    moodLabel: '青绿 · 清爽',
    budgetNote: '低于预算 ¥186',
    elements: [
      { id: 'al-d1', role: '绿植', name: '桌面小绿植', note: '好养，不用天天管。', price: 168, status: 'original', fixed: true },
      { id: 'al-d2', role: '加湿器', name: '香薰加湿器', note: '空调房必备，也能当小夜灯。', price: 288, status: 'original', fixed: true },
      { id: 'al-d3', role: '靠垫', name: '人体工学腰靠', note: '久坐最需要的一件。', price: 158, status: 'original', fixed: true }
    ]
  }
]

/* ── 阶段 1：开场选项 ─────────────────────────────────── */
export const RECIPIENT_OPTIONS = ['女朋友', '男朋友', '妈妈', '爸爸', '长辈', '朋友', '同事']
export const OCCASION_OPTIONS = ['生日', '纪念日', '道歉', '节日', '道谢', '没什么理由']

/** 从购物档案里已沉淀的收礼人（由阶段 5 落库而来，不由用户手动维护） */
export const KNOWN_RECIPIENTS = [
  { id: 'r-mom', name: '妈妈', relation: '母亲', lastGift: '颈部按摩仪', lastFeedback: '常用', likes: ['实用小家电', '护手霜'], avoids: ['香水（过敏）'] }
]

/* ── 阶段 4：贺卡排版风格（不引入字体资源，用现有三套做差异）── */
export const CARD_STYLES = [
  { id: 'plain', label: '简洁', note: '无衬线 · 常规行距' },
  { id: 'soft', label: '温柔', note: '行距放宽 · 字号偏小' },
  { id: 'formal', label: '郑重', note: '图文间距大 · 居中对齐' }
]

/** 包装纸图案：用 CSS 图案参数化生成，不依赖图片素材 */
export const WRAP_PATTERNS = [
  { id: 'plain', label: '素面' },
  { id: 'stripe', label: '细条纹' },
  { id: 'check', label: '小格纹' },
  { id: 'dot', label: '圆点' }
]

export const RIBBON_COLORS = [
  { id: 'gold', label: '暖金', value: '#c9983c' },
  { id: 'clay', label: '陶土', value: '#d85a30' },
  { id: 'moss', label: '苔绿', value: '#639922' },
  { id: 'ink', label: '墨黑', value: '#2b3034' }
]

/** 生成 CSS 图案背景（素面返回空对象） */
export const wrapPatternStyle = (patternId, baseColor) => {
  const c = baseColor || '#ead5a8'
  switch (patternId) {
    case 'stripe':
      return { backgroundImage: `repeating-linear-gradient(90deg, ${c}22 0 6px, transparent 6px 16px)` }
    case 'check':
      return {
        backgroundImage:
          `repeating-linear-gradient(0deg, ${c}22 0 1px, transparent 1px 14px),` +
          `repeating-linear-gradient(90deg, ${c}22 0 1px, transparent 1px 14px)`
      }
    case 'dot':
      return {
        backgroundImage: `radial-gradient(${c}33 1.4px, transparent 1.5px)`,
        backgroundSize: '12px 12px'
      }
    default:
      return {}
  }
}

/* ── 阶段 4：寄语 ───────────────────────────────────────
 * 真实实现里由 agent 依据「累积的批注与替换理由」生成。
 * 这里的拼装逻辑就是素材关系：改动理由 → 寄语里的一句话。 */
export const buildMessage = ({ recipient, occasion, concept, revisions }) => {
  const why = revisions.length
    ? `你说过「${revisions[revisions.length - 1].reason}」，这句我记下了。`
    : '挑的都是你希望她能天天用到的。'
  return `给${recipient || '你'}的${occasion || '这份心意'}：\n\n这一盒叫「${concept?.title || '心意'}」。${concept?.thesis || ''}\n\n${why}\n\n愿你每天都睡得好一点。`
}

/* ── 阶段 5：清单 ─────────────────────────────────────── */
export const RECEIPT_META = {
  title: '礼品清单',
  footnote: '这份清单会同时存入购物档案，下次给同一个人挑礼物时我会记得这些偏好。'
}
