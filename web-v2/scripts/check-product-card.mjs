// 回归检查：商品卡片载荷解析。
//
// 用例里的单卡 JSON 是**从生产环境真实 SSE 流里抓下来的原文**（2026-09-12 探针），
// 不是编造的。修复前 ProductCardTool 只认 data.cards，这些真实载荷会解析出空数组，
// 界面显示「暂无商品数据」。
//
// 运行：node scripts/check-product-card.mjs
import { parseProductCards } from '../src/utils/productCard.js'

// ── 生产环境真实抓包（render_product_card 的 result_content）──
const REAL_SINGLE_CARD = '{"type": "product_card", "data": {"title": "HUAWEI Pura 80 Pro 12GB+512GB 曜白", "price": 0.0, "platform": "京东", "url": "#", "image_url": null, "rating": null, "shop_name": "华为京东自营旗舰店"}}'
const REAL_SINGLE_CARD_2 = '{"type": "product_card", "data": {"title": "Apple 苹果 iPhone 17 Pro 256GB 银色（京东自营 国补）", "price": 0.0, "platform": "京东 Apple 自营官方旗舰店", "url": "#", "image_url": null, "rating": null, "shop_name": "京东 Apple 自营官方旗舰店"}}'

const cases = [
  {
    name: '生产真实载荷 · 单卡（华为）',
    input: REAL_SINGLE_CARD,
    expect: (c) => c.length === 1 && c[0].title.includes('Pura 80'),
  },
  {
    name: '生产真实载荷 · 单卡（iPhone）',
    input: REAL_SINGLE_CARD_2,
    expect: (c) => c.length === 1 && c[0].title.includes('iPhone 17'),
  },
  {
    name: '已解析对象形式（非字符串）',
    input: JSON.parse(REAL_SINGLE_CARD),
    expect: (c) => c.length === 1,
  },
  {
    name: '多卡格式 { cards: [...] }',
    input: '{"cards":[{"title":"A"},{"title":"B"}]}',
    expect: (c) => c.length === 2,
  },
  {
    name: '裸商品对象',
    input: '{"title":"裸对象商品","price":9.9}',
    expect: (c) => c.length === 1 && c[0].price === 9.9,
  },
  { name: '空字符串（无结果）', input: '', expect: (c) => c.length === 0 },
  { name: 'null（无结果）', input: null, expect: (c) => c.length === 0 },
  { name: 'undefined（无结果）', input: undefined, expect: (c) => c.length === 0 },
  { name: '非法 JSON', input: '{不是合法 json', expect: (c) => c.length === 0 },
  { name: '合法但无卡片字段', input: '{"foo":1}', expect: (c) => c.length === 0 },
]

let pass = 0
let fail = 0
console.log('=== 商品卡片解析回归 ===\n')
for (const c of cases) {
  let got
  let ok = false
  try {
    got = parseProductCards(c.input)
    ok = c.expect(got)
  } catch (e) {
    got = `抛错: ${e.message}`
  }
  console.log(`${ok ? '  ✓' : '  ✗'} ${c.name}${ok ? '' : `  → 实得 ${JSON.stringify(got)?.slice(0, 90)}`}`)
  ok ? pass++ : fail++
}

console.log(`\n通过 ${pass} / ${pass + fail}`)
console.log(fail === 0 ? '结论：卡片解析正常 ✓' : '结论：存在失败用例 ✗')
process.exit(fail === 0 ? 0 : 1)
