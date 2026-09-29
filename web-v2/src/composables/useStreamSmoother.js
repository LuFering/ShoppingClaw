// 流式平滑播放器
//
// 问题：后端按 LLM provider 的吐字节奏下发 message_chunk，叠加网络与 provider 侧缓冲后，
// 增量是一阵一阵到达的 —— 界面表现为「卡一会儿不动，然后整段蹦出来」。
//
// 解法：到达的增量先入缓冲，再用 requestAnimationFrame 按自适应速率逐帧播放。
// 播放速率取三者最大值：
//   1) MIN_CHARS_PER_SECOND  —— 观感下限，再慢也保持连续
//   2) arrivalRate           —— 实测到达速率（指数平滑），保证不会慢于真实生成
//   3) 积压量 / CATCH_UP_MS  —— 追赶速率，积压越多放得越快，但用固定时间摊平
// 这样既消除了「一卡一蹦」，又不会因为一次大包而瞬间刷屏。
//
// 差异：msgChunks[id] 是「chunk 数组」的写法不适用，本项目是「单条消息对象、
// content 为累积字符串」，因此这里只把正文增量通过 writeDelta 回调落地，
// 因此不采用 chunk 骨架合并逻辑。

const START_BUFFER_MS = 180 // 起播前先攒一点，避免开头一顿一顿
const RATE_SAMPLE_MS = 200 // 到达速率采样窗口
const RATE_ADJUST_MS = 300 // 速率指数平滑时间常数
const CATCH_UP_MS = 600 // 积压按多少毫秒追完
const MIN_CHARS_PER_SECOND = 32 // 播放速率下限（字符/秒）

// 按「字素」切分：避免把 emoji、组合字符（如 é、👨‍👩‍👧）从中间切开导致乱码
const segmenter =
  typeof Intl !== 'undefined' && typeof Intl.Segmenter === 'function'
    ? new Intl.Segmenter(undefined, { granularity: 'grapheme' })
    : null

const raf =
  typeof window !== 'undefined' && typeof window.requestAnimationFrame === 'function'
    ? (cb) => window.requestAnimationFrame(cb)
    : (cb) => setTimeout(cb, 16)

const caf =
  typeof window !== 'undefined' && typeof window.cancelAnimationFrame === 'function'
    ? (id) => window.cancelAnimationFrame(id)
    : (id) => clearTimeout(id)

/** 以 UTF-16 长度计量预算，实际切片停在完整字素边界。 */
const takeFromBuffer = (value, count) => {
  if (!value || count <= 0) return { emitted: '', rest: value }
  if (count >= value.length) return { emitted: value, rest: '' }
  if (!segmenter) {
    const end = Math.max(1, count)
    return { emitted: value.slice(0, end), rest: value.slice(end) }
  }
  let end = 0
  for (const { segment, index } of segmenter.segment(value)) {
    if (index + segment.length > count && end > 0) break
    end = index + segment.length
    if (end >= count) break
  }
  return { emitted: value.slice(0, end), rest: value.slice(end) }
}

/**
 * @param {Object} options
 * @param {(threadId: string) => Object|null} options.getThreadState 取线程状态（用于判断线程是否还在）
 * @param {(threadId: string, messageId: string, text: string) => void} options.writeDelta
 *        把一段正文增量落到对应消息上（由调用方负责创建消息条目）
 */
export function useStreamSmoother({ getThreadState, writeDelta }) {
  // threadId -> Map<messageId, controller>
  const controllersByThread = new Map()

  /** 立刻交付该消息剩余缓冲，并取消它唯一的帧任务。 */
  const flushMessage = (threadId, messageId) => {
    const controllers = controllersByThread.get(threadId)
    const controller = controllers?.get(messageId)
    if (!controller) return
    if (controller.frameId !== null) caf(controller.frameId)
    controller.frameId = null
    if (controller.buffer) {
      writeDelta(threadId, messageId, controller.buffer)
      controller.buffer = ''
    }
    controllers.delete(messageId)
  }

  /** 播放速度按时间平滑变化，避免包大小或刷新率直接决定出字速度。 */
  const tick = (threadId, messageId) => {
    const controllers = controllersByThread.get(threadId)
    const controller = controllers?.get(messageId)
    if (!controller) return
    controller.frameId = null

    if (!getThreadState(threadId)) {
      controllers.delete(messageId)
      return
    }

    const now = performance.now()
    if (now > controller.lastFrameAt) {
      // 页面恢复 / 长任务之后不把累计帧时间一次兑换成大量正文
      const elapsed = Math.min(now - controller.lastFrameAt, 64)
      controller.lastFrameAt = now
      const targetRate = Math.max(
        MIN_CHARS_PER_SECOND,
        controller.arrivalRate,
        (controller.buffer.length * 1000) / CATCH_UP_MS
      )
      if (controller.rate === 0) controller.rate = targetRate
      controller.rate += (targetRate - controller.rate) * (1 - Math.exp(-elapsed / RATE_ADJUST_MS))
      controller.credit += (controller.rate * elapsed) / 1000

      const budget = Math.floor(controller.credit)
      if (budget > 0) {
        const { emitted, rest } = takeFromBuffer(controller.buffer, budget)
        controller.buffer = rest
        controller.credit -= emitted.length
        if (emitted) writeDelta(threadId, messageId, emitted)
      }
    }

    if (controller.buffer) {
      controller.frameId = raf(() => tick(threadId, messageId))
    } else {
      controllers.delete(messageId)
    }
  }

  /**
   * 累积正文增量。工具参数等非正文内容不走这里，保持即时呈现。
   * @param {string} text 本次到达的正文增量
   * @param {string} threadId
   * @param {string} messageId
   */
  const pushText = (text, threadId, messageId) => {
    if (!text || !threadId || !messageId) return
    const threadState = getThreadState(threadId)
    if (!threadState) return

    // 用户在系统里开了「减少动态效果」：不做延迟播放，直接落地
    const reduceMotion =
      typeof window !== 'undefined' &&
      typeof window.matchMedia === 'function' &&
      window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduceMotion) {
      writeDelta(threadId, messageId, text)
      return
    }

    if (!controllersByThread.has(threadId)) controllersByThread.set(threadId, new Map())
    const controllers = controllersByThread.get(threadId)
    let controller = controllers.get(messageId)
    const now = performance.now()

    if (!controller) {
      controller = {
        buffer: '',
        frameId: null,
        // 起播缓冲：先攒 START_BUFFER_MS 再开始放，避免开头一顿一顿
        lastFrameAt: now + START_BUFFER_MS,
        sampleAt: now,
        sampleChars: 0,
        arrivalRate: 0,
        rate: 0,
        credit: 0
      }
      controllers.set(messageId, controller)
    }

    controller.buffer += text
    controller.sampleChars += text.length
    const sampleMs = now - controller.sampleAt
    if (sampleMs >= RATE_SAMPLE_MS) {
      const observedRate = (controller.sampleChars * 1000) / sampleMs
      const weight = 1 - Math.exp(-sampleMs / RATE_ADJUST_MS)
      controller.arrivalRate += (observedRate - controller.arrivalRate) * weight
      controller.sampleChars = 0
      controller.sampleAt = now
    }

    if (controller.frameId === null) controller.frameId = raf(() => tick(threadId, messageId))
  }

  /** 结束 / 报错 / 中止 / 审批前：同步交付该线程全部缓冲。 */
  const flushThread = (threadId) => {
    const controllers = controllersByThread.get(threadId)
    if (!controllers) return
    for (const messageId of [...controllers.keys()]) flushMessage(threadId, messageId)
    controllersByThread.delete(threadId)
  }

  /** 清除指定线程或全部线程的帧任务，不再向旧消息写入。 */
  const resetThread = (threadId = null) => {
    for (const [id, controllers] of [...controllersByThread]) {
      if (threadId && id !== threadId) continue
      for (const controller of controllers.values()) {
        if (controller.frameId !== null) caf(controller.frameId)
      }
      controllersByThread.delete(id)
    }
  }

  return { pushText, flushThread, resetThread }
}
