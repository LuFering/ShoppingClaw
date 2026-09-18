import { nextTick } from 'vue'

/**
 * 滚动控制工具类
 */
export class ScrollController {
  constructor(containerSelector = '.chat', options = {}) {
    this.containerSelector = containerSelector
    this.options = {
      threshold: 100,
      scrollDelay: 100,
      retryDelays: [50, 150],
      ...options
    }

    this.scrollTimer = null
    this.isUserScrolling = false
    this.shouldAutoScroll = true
    this.isProgrammaticScroll = false

    // ═══ 新消息置顶锚定（pin）═══
    // 发起新一轮时把「这一轮」钉在容器顶部，屏蔽掉上一段对话；
    // 流式输出期间内容都追加在锚点下方，锚点位置不变 → 自然保持置顶；
    // 用户一旦主动滚动就立刻解除，把控制权交还给用户。
    this.pinActive = false
    this.pinnedEl = null
    this.pinObserver = null
    this.pinSelector = ''
    this.pinRaf = null
    this._expectedTop = null
    this._gestureHandlers = null

    // Bind the context of 'this' for the event handler
    this.handleScroll = this.handleScroll.bind(this)
  }

  /**
   * 获取滚动容器
   * @returns {Element|null}
   */
  getContainer() {
    return document.querySelector(this.containerSelector)
  }

  /**
   * 检查是否在底部
   * @returns {boolean}
   */
  isAtBottom() {
    const container = this.getContainer()
    if (!container) return false

    const { threshold } = this.options
    return container.scrollHeight - container.scrollTop - container.clientHeight <= threshold
  }

  /**
   * 处理滚动事件
   */
  handleScroll() {
    if (this.scrollTimer) {
      clearTimeout(this.scrollTimer)
    }

    // 如果是程序性滚动，忽略此次事件
    if (this.isProgrammaticScroll) {
      this.isProgrammaticScroll = false
      return
    }

    // 钉住状态：只有"真实偏离"才解除（例如拖滚动条）。
    // 我们自己每帧强制对齐，位置几乎不动，所以不会误触发；
    // 真正的用户手势（wheel/触摸/方向键）由 _attachGestureRelease 直接解除。
    if (this.pinActive) {
      const container = this.getContainer()
      const expected = this._expectedTop
      const deviated =
        !container || expected == null ? true : Math.abs(container.scrollTop - expected) > 6
      if (deviated) this.clearPin()
    }

    // 标记用户正在滚动
    this.isUserScrolling = true

    // 检查是否在底部
    this.shouldAutoScroll = this.isAtBottom()

    // 滚动结束后一段时间重置用户滚动状态
    this.scrollTimer = setTimeout(() => {
      this.isUserScrolling = false
    }, this.options.scrollDelay)
  }

  /**
   * 等待 DOM 布局稳定
   * @returns {Promise<void>}
   */
  async waitForLayoutStable() {
    // 使用 requestAnimationFrame 确保 DOM 渲染完成
    await new Promise((resolve) => requestAnimationFrame(resolve))
    // 额外等待一小段时间确保 CSS 布局完成
    await new Promise((resolve) => setTimeout(resolve, 50))
  }

  /**
   * 智能滚动到底部
   * @param {boolean} force - 是否强制滚动
   */
  async scrollToBottom(force = false) {
    await nextTick()
    // 等待 DOM 布局稳定
    await this.waitForLayoutStable()

    // 只有在应该自动滚动时才执行（除非强制）
    if (!force && !this.shouldAutoScroll) return

    const container = this.getContainer()
    if (!container) return

    // 标记为程序性滚动
    this.isProgrammaticScroll = true

    // 记录滚动前的容器高度
    const initialHeight = container.scrollHeight

    const scrollOptions = {
      top: container.scrollHeight,
      behavior: 'smooth'
    }

    // 立即滚动
    container.scrollTo(scrollOptions)

    // 多次重试确保滚动成功，包括等待输入框等动态元素布局完成
    const retryDelays = [50, 100, 200, 400]
    retryDelays.forEach((delay, index) => {
      setTimeout(() => {
        if (force || this.shouldAutoScroll) {
          this.isProgrammaticScroll = true
          const behavior = index === retryDelays.length - 1 ? 'auto' : 'smooth'

          // 如果高度变化了，说明可能有动态内容正在渲染，再次等待
          if (container.scrollHeight !== initialHeight && index < retryDelays.length - 1) {
            this.waitForLayoutStable().then(() => {
              container.scrollTo({
                top: container.scrollHeight,
                behavior
              })
            })
          } else {
            container.scrollTo({
              top: container.scrollHeight,
              behavior
            })
          }
        }
      }, delay)
    })
  }

  async scrollToBottomStaticForce() {
    const container = this.getContainer()
    if (!container) return

    // 标记为程序性滚动
    this.isProgrammaticScroll = true

    const scrollOptions = {
      top: container.scrollHeight,
      behavior: 'auto'
    }

    container.scrollTo(scrollOptions)
  }

  /**
   * 把元素钉在容器顶部（新一轮对话置顶，屏蔽掉上一段对话）。
   *
   * 关键：不能只"对齐一次"。实测只对齐一次会被随后的布局抖动/其它滚动带走，
   * 所以钉住期间用 requestAnimationFrame **持续强制** scrollTop = 锚点位置；
   * 元素若被 Vue 重渲染替换，按 selector 重新取（自愈）。
   * 解除只认真实用户手势（wheel / touchstart / 方向键）与明显的位置偏离。
   */
  async pinToSelector(selector, { maintain = true, waitMs = 1500 } = {}) {
    this.clearPin()
    this.pinSelector = selector || ''
    this.pinActive = true
    // 钉住期间禁止自动贴底，否则会被 scrollToBottom 拉走
    this.shouldAutoScroll = false

    await nextTick()
    await this.waitForLayoutStable()
    if (!this.pinActive) return

    // 元素可能还没渲染出来（异步会话/消息加载），等一会儿
    if (this.pinSelector && waitMs > 0) await this._waitForElement(this.pinSelector, waitMs)
    if (!this.pinActive) return

    this._enforcePin()
    if (maintain) {
      this._startPinMaintain()
      this._attachGestureRelease()
    }
  }

  /** 兼容旧调用：直接传元素 */
  async pinElementToTop(el, options = {}) {
    if (!el) return
    await this.pinToSelector(null, options)
    this.pinnedEl = el
    this._enforcePin()
  }

  async _waitForElement(selector, timeout) {
    const started = Date.now()
    while (Date.now() - started < timeout) {
      const nodes = document.querySelectorAll(selector)
      if (nodes.length) return nodes[nodes.length - 1]
      await new Promise((r) => setTimeout(r, 60))
    }
    return null
  }

  /** 解析锚点元素：给定 selector 时每次都重新取最后一个（跟随最新一轮，且能自愈重渲染） */
  _resolveEl() {
    if (this.pinSelector) {
      const nodes = document.querySelectorAll(this.pinSelector)
      if (nodes.length) this.pinnedEl = nodes[nodes.length - 1]
    }
    return this.pinnedEl && this.pinnedEl.isConnected ? this.pinnedEl : null
  }

  /** 强制：把锚点压回容器顶部 */
  _enforcePin() {
    const container = this.getContainer()
    const el = this._resolveEl()
    if (!container || !el) return

    const top = Math.max(
      0,
      Math.round(
        el.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop
      )
    )
    this._expectedTop = top
    if (Math.abs(container.scrollTop - top) < 1) return

    this.isProgrammaticScroll = true
    // 直接赋值而非 scrollTo(behavior:'smooth')：避免动画期间被中途打断
    container.scrollTop = top
  }

  _startPinMaintain() {
    this._stopPinMaintain()
    if (typeof requestAnimationFrame === 'undefined') return
    const tick = () => {
      if (!this.pinActive) {
        this.pinRaf = null
        return
      }
      this._enforcePin()
      this.pinRaf = requestAnimationFrame(tick)
    }
    this.pinRaf = requestAnimationFrame(tick)
  }

  _stopPinMaintain() {
    if (this.pinRaf) {
      cancelAnimationFrame(this.pinRaf)
      this.pinRaf = null
    }
    if (this.pinObserver) {
      this.pinObserver.disconnect()
      this.pinObserver = null
    }
  }

  /** 用户主动滚动的手势 → 解除钉住（程序性滚动不会产生这些事件） */
  _attachGestureRelease() {
    this._detachGestureRelease()
    const container = this.getContainer()
    if (!container) return
    const onWheel = () => this.releasePin()
    const onTouch = () => this.releasePin()
    const onKey = (e) => {
      const keys = ['ArrowUp', 'ArrowDown', 'PageUp', 'PageDown', 'Home', 'End', ' ']
      if (keys.includes(e.key)) this.releasePin()
    }
    this._gestureHandlers = [
      ['wheel', onWheel],
      ['touchstart', onTouch],
      ['keydown', onKey]
    ]
    for (const [type, fn] of this._gestureHandlers) {
      container.addEventListener(type, fn, { passive: true })
    }
  }

  _detachGestureRelease() {
    const container = this.getContainer()
    if (!container || !this._gestureHandlers) return
    for (const [type, fn] of this._gestureHandlers) {
      container.removeEventListener(type, fn)
    }
    this._gestureHandlers = null
  }

  /** 解除钉住：保留当前滚动位置，用户可从这里往下完整阅读 */
  releasePin() {
    if (!this.pinActive) return
    this.clearPin()
    this.shouldAutoScroll = this.isAtBottom()
  }

  clearPin() {
    this._stopPinMaintain()
    this._detachGestureRelease()
    this.pinActive = false
    this.pinnedEl = null
    this.pinSelector = ''
    this._expectedTop = null
  }

  /**
   * 启用自动滚动
   */
  enableAutoScroll() {
    this.shouldAutoScroll = true
  }

  /**
   * 禁用自动滚动
   */
  disableAutoScroll() {
    this.shouldAutoScroll = false
  }

  /**
   * 获取滚动状态
   */
  getScrollState() {
    return {
      isUserScrolling: this.isUserScrolling,
      shouldAutoScroll: this.shouldAutoScroll,
      isAtBottom: this.isAtBottom()
    }
  }

  /**
   * 清理定时器
   */
  cleanup() {
    this.clearPin()
    if (this.scrollTimer) {
      clearTimeout(this.scrollTimer)
      this.scrollTimer = null
    }
  }

  /**
   * 重置滚动状态
   */
  reset() {
    this.cleanup()
    this.isUserScrolling = false
    this.shouldAutoScroll = true
    this.isProgrammaticScroll = false
    this.pinActive = false
    this.pinnedEl = null
  }
}

/**
 * 创建默认的滚动控制器实例
 */
export const createScrollController = (containerSelector, options) => {
  return new ScrollController(containerSelector, options)
}

export default ScrollController
