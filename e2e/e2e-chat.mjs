// ShoppingClaw 对话模块端到端测试
//
// 做什么：真浏览器登录 → 发一条真实需求 → 全程高频采样 DOM，量化三件事
//   1. 流式平滑度：正文增量的大小分布（Yuxi 效果 = 小而密，而非「卡住后一大段」）
//   2. 工具状态：是否还有停在「正在调用工具」的行、同一次调用是否重复成行
//   3. 商品卡片：流式期间与结束后是否都在
//
// 用法：node e2e-chat.mjs ["需求文本"]
import { chromium } from 'file:///C:/Users/25153/.workbuddy-ai/binaries/node/workspace/node_modules/playwright-core/index.mjs'

const BASE = 'http://111.229.209.47'
const USER = 'zzverify'
const PASS = 'ZvTest2026sc'
const QUERY = process.argv[2] || '对比 iPhone 17 和华为 Pura 80'
const MAX_WAIT_MS = 7 * 60 * 1000
const SAMPLE_MS = 150
const SHOT_DIR = 'C:/Users/25153/workbuddy-ai/虾购/e2e'

const browser = await chromium.connectOverCDP('http://127.0.0.1:9222')
const ctx = browser.contexts()[0] || (await browser.newContext())
const page = await ctx.newPage()

const errors = []
page.on('pageerror', (e) => errors.push(`[pageerror] ${e.message}`))
page.on('console', (m) => {
  if (m.type() === 'error') errors.push(`[console] ${m.text().slice(0, 180)}`)
})

const log = (...a) => console.log(...a)

// ── 1. 登录 ──────────────────────────────────────────────
log('▸ 登录…')
await page.goto(`${BASE}/login`, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForTimeout(1500)

const needLogin = await page.locator('#form_item_loginId').count()
if (needLogin) {
  await page.fill('#form_item_loginId', USER)
  await page.fill('#form_item_password', PASS)
  await page.click('button:has-text("登录")')
  await page.waitForTimeout(3500)
} else {
  log('  已有登录态，跳过')
}
log('  当前 URL:', page.url())
if (page.url().includes('/login')) {
  log('  ✗ 登录失败，终止')
  await page.screenshot({ path: `${SHOT_DIR}/e2e-login-fail.png` })
  await page.close()
  await browser.close()
  process.exit(1)
}

// 每轮跑在全新对话里，避免上一轮的消息干扰采样。
// 带 cache-buster：否则浏览器可能仍加载旧 hash 的 bundle，测的是旧代码。
await page.goto(`${BASE}/agent?t=${Date.now()}`, { waitUntil: 'networkidle', timeout: 60000 })
await page.waitForTimeout(2000)
// 侧栏按钮常被主区浮层遮挡，直接触发 click 事件更稳
const clicked = await page.evaluate(() => {
  const btn = document.querySelector('.new-chat-btn')
  if (!btn) return false
  btn.click()
  return true
})
if (clicked) {
  await page.waitForTimeout(2500)
  log('  已新建对话')
}

// ── 2. 发包 ──────────────────────────────────────────────
log(`▸ 发送需求：${QUERY}`)
await page.waitForSelector('textarea.user-input', { timeout: 30000 })
await page.fill('textarea.user-input', QUERY)
await page.waitForTimeout(400)
const sent = await page.evaluate(() => {
  const btn = document.querySelector('button.send-button')
  if (!btn || btn.disabled) return false
  btn.click()
  return true
})
if (!sent) {
  log('  ✗ 发送按钮不可用，终止')
  await page.screenshot({ path: `${SHOT_DIR}/e2e-send-fail.png` })
  await page.close()
  await browser.close()
  process.exit(1)
}

// ── 3. 采样 ──────────────────────────────────────────────
const samples = []
const t0 = Date.now()
let lastLen = -1
let sentCount = -1

const readState = () =>
  page.evaluate(() => {
    const box = document.querySelector('.chat-box') || document.body
    const boxText = box.innerText || ''
    // 只统计 AI 正文元素，避免工具摘要、卡片标题等文字污染流式平滑度指标
    const mds = [...document.querySelectorAll('.assistant-message .message-md')].map(
      (el) => (el.innerText || '').length
    )
    const toolRows = [...document.querySelectorAll('.tool-call-display')].map((el) => {
      const txt = (el.innerText || '').replace(/\s+/g, ' ').trim()
      let status = 'unknown'
      // 普通工具行用「正在调用工具 / 执行完成 / 执行失败」，
      // 子智能体行用「运行中 / 已完成 / 已失败」，两种文案都要认。
      if (/正在调用工具|运行中/.test(txt)) status = 'running'
      else if (/执行完成|已完成/.test(txt)) status = 'completed'
      else if (/执行失败|已失败/.test(txt)) status = 'failed'
      return { status, label: txt.slice(0, 60) }
    })
    return {
      mdTotal: mds.reduce((a, b) => a + b, 0),
      mdCount: mds.length,
      mdLast: mds.length ? mds[mds.length - 1] : 0,
      boxLen: boxText.length,
      cards: document.querySelectorAll('.product-card').length,
      emptyCard: boxText.includes('暂无商品数据'),
      pendingCard: boxText.includes('等待商品数据'),
      runningText: /正在调用工具|运行中/.test(boxText),
      toolSummary: (document.querySelector('.tool-group-summary, .tool-calls-summary')?.innerText || '').slice(0, 80),
      toolRows,
      generating: !!document.querySelector('.generating-status'),
    }
  })

let shot30 = false
let shot60 = false
let stableRounds = 0

while (Date.now() - t0 < MAX_WAIT_MS) {
  let st
  try {
    st = await readState()
  } catch (e) {
    log('  采样异常:', e.message)
    break
  }
  const t = (Date.now() - t0) / 1000
  const delta = lastLen < 0 ? 0 : st.mdTotal - lastLen
  samples.push({ t, ...st, delta })
  lastLen = st.mdTotal

  if (!shot30 && t > 30) {
    shot30 = true
    await page.screenshot({ path: `${SHOT_DIR}/e2e-t30.png`, fullPage: true })
  }
  if (!shot60 && t > 60) {
    shot60 = true
    await page.screenshot({ path: `${SHOT_DIR}/e2e-t60.png`, fullPage: true })
  }

  // 收尾判定：生成标志消失，且连续 6 次采样长度不再变化
  if (!st.generating && delta === 0) {
    stableRounds += 1
    if (stableRounds >= 6) break
  } else {
    stableRounds = 0
  }
  sentCount = samples.length
  await page.waitForTimeout(SAMPLE_MS)
}

const dur = (Date.now() - t0) / 1000
await page.screenshot({ path: `${SHOT_DIR}/e2e-final.png`, fullPage: true })

// ── 4. 报告 ──────────────────────────────────────────────
const final = samples[samples.length - 1] || {}

log(`\n▸ 结束，用时 ${dur.toFixed(1)}s，采样 ${samples.length} 次`)

// 4.1 平滑度：只看「有正文增长」的采样点
const growth = samples.filter((s) => s.delta > 0)
const deltas = growth.map((s) => s.delta)
const stalls = []
for (let i = 1; i < samples.length; i += 1) {
  if (samples[i].delta === 0 && samples[i].t < dur - 1) stalls.push(samples[i].t)
}
// 把连续停顿合并成区间
const stallRanges = []
let cur = null
for (const t of stalls) {
  if (cur && t - cur.end <= SAMPLE_MS / 1000 + 0.05) cur.end = t
  else {
    if (cur) stallRanges.push(cur)
    cur = { start: t, end: t }
  }
}
if (cur) stallRanges.push(cur)
const longStalls = stallRanges.filter((r) => r.end - r.start > 1.0)

log('\n=== 1. 流式平滑度（只统计 AI 正文）===')
log(`  正文总字数: ${final.mdTotal}  消息数: ${final.mdCount}`)
log(`  有增长的采样点: ${growth.length} / ${samples.length}`)
if (deltas.length) {
  const sorted = [...deltas].sort((a, b) => b - a)
  const sum = deltas.reduce((a, b) => a + b, 0)
  log(`  单次增长量: 最大 ${sorted[0]} / 中位 ${sorted[Math.floor(sorted.length / 2)]} / 总计 ${sum}`)
  log(`  最大一次增长占总量: ${((sorted[0] / sum) * 100).toFixed(1)}%  ← 越低越平滑`)
  const big = growth.filter((s) => s.delta > 100)
  log(`  增长量 >100 字的次数: ${big.length}  ← 这些就是「整段蹦出」`)
  big.slice(0, 8).forEach((s) => log(`     @${s.t.toFixed(1)}s 一次 +${s.delta} 字（消息数 ${s.mdCount}）`))
  // 消息数从 N 跳到 N+1 说明换了条消息（可能是历史回读替换）
  const jumps = []
  for (let i = 1; i < samples.length; i += 1) {
    if (samples[i].mdCount !== samples[i - 1].mdCount) {
      jumps.push(`@${samples[i].t.toFixed(1)}s 消息数 ${samples[i - 1].mdCount}→${samples[i].mdCount}`)
    }
  }
  log(`  消息条数变化: ${jumps.length ? jumps.join(' | ') : '无'}`)
}
log(`  >1s 的停顿: ${longStalls.length} 次`)
for (const r of longStalls.slice(0, 8)) {
  log(`     ${r.start.toFixed(1)}s → ${r.end.toFixed(1)}s（${(r.end - r.start).toFixed(1)}s）`)
}

// 4.2 工具行
log('\n=== 2. 工具行 ===')
log(`  结束后页面出现「正在调用工具」: ${final.runningText}`)
log(`  结束时的工具摘要: ${final.toolSummary || '（无）'}`)
// 「正在调用工具」连续出现的区间：正常应随工具完成而消失
const spans = []
let curSpan = null
for (const s of samples) {
  if (s.runningText) {
    if (curSpan) curSpan.end = s.t
    else curSpan = { start: s.t, end: s.t }
  } else if (curSpan) {
    spans.push(curSpan)
    curSpan = null
  }
}
if (curSpan) spans.push(curSpan)
const longest = spans.reduce((m, s) => Math.max(m, s.end - s.start), 0)
log(`  「正在调用工具」出现区间数: ${spans.length}，最长连续 ${longest.toFixed(1)}s`)
log(`  结束瞬间是否仍在转圈: ${final.runningText ? '✗ 是' : '✓ 否'}`)
const stillRunning = final.toolRows.filter((r) => r.status === 'running')
if (stillRunning.length) stillRunning.forEach((r) => log(`     ${r.label}`))

// 4.3 卡片
log('\n=== 3. 商品卡片 ===')
log(`  最终卡片数: ${final.cards}`)
log(`  出现「暂无商品数据」: ${final.emptyCard}`)
log(`  出现「等待商品数据」: ${final.pendingCard}`)
const duringCards = samples.filter((s) => s.cards > 0).length
log(`  流式期间出现过卡片的采样点: ${duringCards} / ${samples.length}`)

// 4.4 控制台错误
log('\n=== 4. 控制台错误 ===')
const uniq = [...new Set(errors)]
log(`  共 ${errors.length} 条（去重 ${uniq.length}）`)
uniq.slice(0, 8).forEach((e) => log(`   ${e}`))

log(`\n截图: e2e-t30.png / e2e-t60.png / e2e-final.png`)

await page.close()
await browser.close()
