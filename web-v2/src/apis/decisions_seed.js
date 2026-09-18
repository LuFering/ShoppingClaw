// 购物档案种子数据（初次加载 / 重置时使用）
// 结构对齐后端将来 decisions 表：phase 状态机 + 分段字段
const now = Date.now()
const days = (n) => now - n * 86400000
const isoDays = (n) => new Date(now - n * 86400000).toISOString().slice(0, 10)
const rel = (ts) => {
  const d = Math.max(1, Math.round((now - ts) / 86400000))
  return d <= 1 ? '昨天' : d <= 7 ? `${d}天前` : `${Math.round(d / 7)}周前`
}

const mk = (o) => {
  const ts = o.ts ?? now
  return {
    id: o.id, phase: o.phase, source: o.source || 'manual',
    target: o.target, category: o.category || '',
    note: o.note || o.rawIdea || '', rawIdea: o.rawIdea || '',
    budget: o.budget || '', forWhom: o.forWhom || '', scenario: o.scenario || '',
    aiSummary: o.aiSummary || '',
    candidates: o.candidates || [],
    aiRecommend: o.aiRecommend || '', recReason: o.recReason || '', risk: o.risk || '', bestPrice: o.bestPrice || '',
    dealPrice: o.dealPrice || '', purchasedAt: o.purchasedAt || '',
    reviewNote: o.reviewNote || '', dropNote: o.dropNote || '',
    reminders: o.reminders || [], threadId: o.threadId || null,
    ts, updatedAt: rel(ts)
  }
}

export const seedRecords = () => [
  // ---- 需求池 ----
  mk({ id: 'nd-1', phase: 'need', source: 'ai_draft', target: '冰箱', category: '家电 · 给爸妈', ts: now - 600000,
    note: '给爸妈换对开门大冰箱，静音省电优先，含安装尺寸确认', rawIdea: '给爸妈换个省心的大冰箱',
    budget: '¥5000–7000', forWhom: '爸妈', scenario: '家用',
    aiSummary: '看中海尔 501L 变频对开门（约 ¥5699）：静音 38dB、一级能效；注意散热空间' }),
  mk({ id: 'nd-2', phase: 'need', target: '加湿器', category: '家电 · 卧室', ts: days(2),
    note: '冬天卧室太干，想要静音、大容量，最好上加水', rawIdea: '卧室太干了，想要个静音加湿器', budget: '¥300 内', forWhom: '自己', scenario: '卧室' }),
  mk({ id: 'nd-3', phase: 'need', target: '妈妈的生日礼物', category: '送礼', ts: days(1),
    note: '下个月妈妈生日，预算一千内，偏实用，不要闲置', rawIdea: '妈妈生日礼物，一千内实用型', budget: '¥1000 内', forWhom: '妈妈', scenario: '送礼' }),
  // ---- 候选中 ----
  mk({ id: 'cd-1', phase: 'candidate', target: '扫地机器人', category: '家电 · 自用', ts: days(2),
    note: '扫拖一体，预算 3000，家里有地毯', budget: '¥3000',
    candidates: [
      { id: 'c1', name: '石头 G20', price: '¥2799', note: '全能基站 + 自动集尘；注意地毯识别', chosen: true },
      { id: 'c2', name: '科沃斯 T20', price: '¥2999', note: '避障更好，价格偏高', chosen: false }
    ],
    risk: '水箱对大面积偏小' }),
  mk({ id: 'cd-2', phase: 'candidate', target: '投影仪', category: '数码 · 客厅', ts: days(4),
    note: '卧室用，预算 3000，暗光环境为主', budget: '¥3000',
    candidates: [
      { id: 'c1', name: '极米 Z7X', price: '¥2999', note: '亮度与噪音平衡好', chosen: true },
      { id: 'c2', name: '当贝 D5X', price: '¥2899', note: '白天亮度不足', chosen: false }
    ] }),
  // ---- 已决策 ----
  mk({ id: 'dc-1', phase: 'decided', target: '安全座椅', category: '母婴 · 3岁', ts: days(7),
    note: '安全优先，i-Size 认证，预算不限，考虑旋转款', budget: '预算不限',
    aiRecommend: 'Cybex Sirona（旋转款）', bestPrice: '目标 ¥2599 以内',
    recReason: 'i-Size 认证 + 侧撞防护；安装略复杂，建议门店试装', risk: '安装方向与走线易出错',
    reminders: ['等 618 大促，可叠加以旧换新', '到手后拍照让 AI 复核安装'], threadId: 'th-3' }),
  mk({ id: 'dc-2', phase: 'decided', target: '显示器', category: '数码 · 办公', ts: days(5),
    note: '27 寸 4K，Type-C 反向充电，预算 2500', budget: '¥2500',
    aiRecommend: 'LG 27UP850N', bestPrice: '¥2399 · 现货',
    recReason: '4K + 广色域 + 95W 反向供电', risk: '漏光品控要抽奖，建议自营',
    reminders: ['下单前确认接口供电', '到手测坏点'] }),
  mk({ id: 'dc-3', phase: 'decided', target: '洗烘一体机', category: '家电 · 装修', ts: days(6),
    note: '预算 6000，洗烘一体，家里有老人', budget: '¥6000',
    aiRecommend: '小天鹅洗烘套装', bestPrice: '¥5499 · 待拍板',
    recReason: '洗净比与烘干容量匹配', risk: '安装尺寸要复核',
    reminders: ['装修完工再下单，避免灰尘', '确认阳台水电点位'] }),
  // ---- 使用中 ----
  mk({ id: 'us-1', phase: 'using', target: '洗地机', category: '家电 · 给爸妈', ts: days(1),
    note: '预算 5000，要静音好打理，续航够 150㎡', budget: '¥5000',
    aiRecommend: '添可芙万 3.0', bestPrice: '成交 ¥2199 / 低于目标 ¥801',
    recReason: '静音与自清洁达标，续航覆盖 150㎡；注意拖布耗材成本', risk: '耗材为长期成本；有地毯需另购配件',
    dealPrice: '¥2199', purchasedAt: isoDays(1),
    reminders: ['拖布约 3 个月一换（¥60/对），建议设提醒', '价格有波动，已在盯价'], threadId: 'th-1' }),
  mk({ id: 'us-2', phase: 'using', target: '降噪耳机', category: '数码 · 通勤', ts: days(3),
    note: '通勤地铁用降噪，预算 1500 内，佩戴舒适优先', budget: '¥1500',
    aiRecommend: '索尼 WH-1000XM5', bestPrice: '入手 ¥1499 / 自选 BOSE',
    recReason: '降噪与佩戴舒适均衡；注意溢价与渠道', risk: '非国行注意保修',
    dealPrice: '¥1499', purchasedAt: isoDays(3),
    candidates: [
      { id: 'c1', name: '索尼 WH-1000XM5', price: '¥1999', note: 'AI 推荐', chosen: false },
      { id: 'c2', name: 'BOSE QC45', price: '¥1499', note: '自选，重舒适', chosen: true }
    ],
    reminders: ['已记录偏好：重舒适轻降噪'] }),
  mk({ id: 'us-3', phase: 'using', target: '空气炸锅', category: '家电 · 自用', ts: days(9),
    note: '5L 左右，预算 400 内，好清洗', budget: '¥400',
    aiRecommend: '美的 KZ50E', bestPrice: '成交 ¥339', risk: '涂层久了易粘，用硅胶垫',
    dealPrice: '¥339', purchasedAt: isoDays(9),
    reminders: ['涂层保修 3 年，保留发票'] }),
  mk({ id: 'us-4', phase: 'using', target: '咖啡机', category: '家电 · 自用', ts: days(20),
    note: '意式半自动，预算 2000，新手友好', budget: '¥2000',
    aiRecommend: '德龙 EC9355', bestPrice: '成交 ¥1899', risk: '豆仓需勤清',
    dealPrice: '¥1899', purchasedAt: isoDays(20),
    reminders: ['每季度除垢一次，设提醒'] }),
  mk({ id: 'us-5', phase: 'using', target: '行李箱', category: '出行 · 通勤', ts: days(15),
    note: '20 寸登机箱，预算 800，耐磨轻', budget: '¥800',
    aiRecommend: '地平线 8 号', bestPrice: '入手 ¥749', risk: '拉链款与铝框款选择依据',
    dealPrice: '¥749', purchasedAt: isoDays(15),
    reminders: ['已记录：轻量优先'] }),
  mk({ id: 'us-6', phase: 'using', target: '电动牙刷', category: '个护 · 自用', ts: days(30),
    note: '预算 300，续航久、刷头好买', budget: '¥300',
    aiRecommend: '飞利浦 HX68', bestPrice: '成交 ¥269', risk: '充电座易发霉，注意通风',
    dealPrice: '¥269', purchasedAt: isoDays(30),
    reminders: ['3 个月换一次刷头'] }),
  // ---- 已放弃 ----
  mk({ id: 'dp-1', phase: 'dropped', target: '儿童学习桌', category: '母婴 · 6岁', ts: days(12),
    note: '可升降学习桌，预算 1500，不占地方', budget: '¥1500',
    recReason: '升降与桌面分区合理', dropNote: '孩子更想要卡通款，尊重选择' })
]

export default seedRecords
