/**
 * 语义 token → 真实色值。
 *
 * canvas 渲染的组件（G6 图谱、ECharts 图表）吃不了 `var(--bg-surface)` 这种字符串，
 * 必须先在 JS 里把 CSS 变量解析成具体色值。这一层就是干这个的。
 *
 * 为什么要缓存：一次力导向布局会触发上百轮样式求值，
 * 每个节点/边都调一次 getComputedStyle 会明显拖慢渲染。
 * 这里按 TTL 缓存整份结果，主题切换最多滞后 TTL 生效。
 */

/** 兜底值（取 main.css 的 :root），仅在拿不到 CSS 变量时使用 */
const DEFAULTS = {
  '--bg-base': '#f6f7f5',
  '--bg-surface': '#ffffff',
  '--bg-raised': '#ffffff',
  '--bg-sunken': '#eef0ed',
  '--border': '#e4e6e1',
  '--border-strong': '#d2d5cf',
  '--text-strong': '#15181b',
  '--text': '#2b3034',
  '--text-muted': '#6b727a',
  '--text-faint': '#9aa0a6',
  '--accent-500': '#178a67',
  '--accent-solid': '#0f6349',
  '--pos': '#1f9d5b',
  '--neg': '#d6543f',
  '--warn': '#c98a1b',
  '--info': '#3b82c4'
}

/** 这两个是 canvas 里最常用的，单独快取一份避免解构开销 */
const TOKENS = Object.keys(DEFAULTS)

const TTL = 800

let cache = null
let cacheAt = 0

const readAll = () => {
  if (typeof window === 'undefined' || !document?.documentElement) {
    return { ...DEFAULTS }
  }
  const style = getComputedStyle(document.documentElement)
  const out = {}
  for (const token of TOKENS) {
    const v = style.getPropertyValue(token).trim()
    out[token] = v || DEFAULTS[token]
  }
  return out
}

/** 整份读取（带 TTL 缓存）。键名就是 token 本身，如 colors['--bg-surface'] */
export const themeColors = () => {
  const now = Date.now()
  if (!cache || now - cacheAt > TTL) {
    cache = readAll()
    cacheAt = now
  }
  return cache
}

/** 读单个 token */
export const themeColor = (token, fallback = '') => {
  const all = themeColors()
  return all[token] || fallback || DEFAULTS[token] || ''
}

/** 主题切换后主动失效（可选调用，不调也会在 TTL 后自动刷新） */
export const refreshThemeColors = () => {
  cache = null
  cacheAt = 0
}

export default themeColors
