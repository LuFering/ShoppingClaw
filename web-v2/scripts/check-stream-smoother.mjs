// 回归检查：验证 useStreamSmoother 是否真的把「一阵一阵」的增量摊平。
//
// 背景：后端按 provider 吐字节奏发包，直写 DOM 会出现「卡一会儿 → 整段蹦出」。
// 本脚本模拟三阵到达（间隔 500ms），断言输出被摊成连续多帧。
//
// 运行：node scripts/check-stream-smoother.mjs
import { useStreamSmoother } from '../src/composables/useStreamSmoother.js'

const threadId = 't1'
const messageId = 'm1'
const state = { content: '' }
const events = []
const t0 = Date.now()

const smoother = useStreamSmoother({
  getThreadState: () => ({ ok: true }),
  writeDelta: (_tid, _mid, text) => {
    state.content += text
    events.push({ at: Date.now() - t0, chars: text.length })
  }
})

// 模拟后端：三阵到达，每阵之间停顿 500ms（典型的 provider 缓冲节奏）
const bursts = [
  'iPhone 17 与华为 Pura 80 的对比'.repeat(3),
  '性能方面'.repeat(8),
  '价格方面'.repeat(10)
]
let i = 0
const feed = () => {
  if (i >= bursts.length) {
    setTimeout(() => {
      smoother.flushThread(threadId)
      report()
    }, 1500)
    return
  }
  const burst = bursts[i++]
  console.log(`[${Date.now() - t0}ms] 后端一次送达 ${burst.length} 字`)
  smoother.pushText(burst, threadId, messageId)
  setTimeout(feed, 500)
}
feed()

function report() {
  const total = events.length
  const chars = events.reduce((n, e) => n + e.chars, 0)
  const gaps = events.slice(1).map((e, idx) => e.at - events[idx].at)
  const maxGap = gaps.length ? Math.max(...gaps) : 0
  const maxStep = events.reduce((n, e) => Math.max(n, e.chars), 0)

  console.log('\n=== 播放结果 ===')
  console.log(`落帧次数: ${total}  总字数: ${chars}`)
  console.log(`单帧最大字数: ${maxStep}（越小越平滑）`)
  console.log(`相邻帧最大间隔: ${maxGap}ms`)
  console.log(`首帧出现于: ${events[0]?.at}ms（应有 ~180ms 起播缓冲）`)
  console.log(`内容完整: ${state.content === bursts.join('')}`)

  const ok = total > 10 && maxStep <= 60 && maxGap < 400 && state.content === bursts.join('')
  console.log(ok ? '\n结论：平滑生效 ✓' : '\n结论：未达预期 ✗')
  process.exit(ok ? 0 : 1)
}
