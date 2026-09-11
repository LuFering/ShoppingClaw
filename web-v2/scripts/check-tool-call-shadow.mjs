// 回归检查：工具调用「影子事件」合并。
//
// 用例里的 id 形态取自生产环境真实抓包：
//   权威：call_455385b2ea1d444189aa7ba9（LangChain id，带 message_id）
//   影子：call_render_product_card_eb532e408f88（LifecycleHandler 现算，无 message_id）
//
// 运行：node scripts/check-tool-call-shadow.mjs
import { planShadowReconcile, isShadowToolCallId } from '../src/utils/toolCallShadow.js'

const NOW = 1_700_000_000_000
const AUTH_ID = 'call_455385b2ea1d444189aa7ba9'
const SHADOW_ID = 'call_render_product_card_eb532e408f88'

const cases = [
  {
    name: '影子事件到达 → 并入同名权威记录',
    incoming: { name: 'render_product_card', toolCallId: SHADOW_ID, messageId: null },
    existing: [{ name: 'render_product_card', toolCallId: AUTH_ID, messageId: 'lc_run-1', createdAt: NOW - 10 }],
    expect: (p) => p.mergeInto?.toolCallId === AUTH_ID && p.dropIds.length === 0,
  },
  {
    name: '权威事件到达 → 清掉近期影子行',
    incoming: { name: 'render_product_card', toolCallId: AUTH_ID, messageId: 'lc_run-1' },
    existing: [{ name: 'render_product_card', toolCallId: SHADOW_ID, messageId: null, createdAt: NOW - 10 }],
    expect: (p) => p.dropIds.includes(SHADOW_ID) && p.mergeInto === null,
  },
  {
    name: '超过合并窗口 → 不合并（避免误并两次真实调用）',
    incoming: { name: 'search_products', toolCallId: SHADOW_ID, messageId: null },
    existing: [{ name: 'search_products', toolCallId: AUTH_ID, messageId: 'lc_run-1', createdAt: NOW - 60000 }],
    expect: (p) => p.mergeInto === null && p.dropIds.length === 0,
  },
  {
    name: '不同工具名 → 不合并',
    incoming: { name: 'get_price', toolCallId: SHADOW_ID, messageId: null },
    existing: [{ name: 'search_products', toolCallId: AUTH_ID, messageId: 'lc_run-1', createdAt: NOW - 10 }],
    expect: (p) => p.mergeInto === null,
  },
  {
    name: '目标本身也是影子行 → 不合并（两条影子各留一行）',
    incoming: { name: 'render_product_card', toolCallId: SHADOW_ID, messageId: null },
    existing: [{ name: 'render_product_card', toolCallId: 'call_render_product_card_aaaaaaaaaaaa', messageId: null, createdAt: NOW - 10 }],
    expect: (p) => p.mergeInto === null,
  },
  {
    name: '权威事件不会去清同名权威行',
    incoming: { name: 'search_products', toolCallId: 'call_bbb', messageId: 'lc_run-2' },
    existing: [{ name: 'search_products', toolCallId: AUTH_ID, messageId: 'lc_run-1', createdAt: NOW - 10 }],
    expect: (p) => p.dropIds.length === 0,
  },
  {
    name: 'name 为 unknown → 一律不动',
    incoming: { name: 'unknown', toolCallId: SHADOW_ID, messageId: null },
    existing: [{ name: 'unknown', toolCallId: AUTH_ID, messageId: 'lc_run-1', createdAt: NOW - 10 }],
    expect: (p) => p.mergeInto === null && p.dropIds.length === 0,
  },
  {
    name: 'existing 为空 → 安全返回',
    incoming: { name: 'search_products', toolCallId: SHADOW_ID, messageId: null },
    existing: [],
    expect: (p) => p.mergeInto === null && p.dropIds.length === 0,
  },
]

// id 形态识别
const idCases = [
  [SHADOW_ID, true],
  ['call_search_products_ab12cd34ef56', true],
  [AUTH_ID, false],
  ['call_455385b2ea1d444189aa7ba9', false],
  ['', false],
  [null, false],
]

let pass = 0
let fail = 0
console.log('=== 影子事件合并回归 ===\n')
for (const c of cases) {
  let got
  let ok = false
  try {
    got = planShadowReconcile({ incoming: c.incoming, existing: c.existing, now: NOW })
    ok = c.expect(got)
  } catch (e) {
    got = `抛错: ${e.message}`
  }
  console.log(`${ok ? '  ✓' : '  ✗'} ${c.name}${ok ? '' : `  → 实得 ${JSON.stringify(got)}`}`)
  ok ? pass++ : fail++
}

console.log('\n=== 影子 id 形态识别 ===')
for (const [id, want] of idCases) {
  const got = isShadowToolCallId(id)
  const ok = got === want
  console.log(`${ok ? '  ✓' : '  ✗'} ${JSON.stringify(id)} → ${got}`)
  ok ? pass++ : fail++
}

console.log(`\n通过 ${pass} / ${pass + fail}`)
console.log(fail === 0 ? '结论：影子合并逻辑正常 ✓' : '结论：存在失败用例 ✗')
process.exit(fail === 0 ? 0 : 1)
