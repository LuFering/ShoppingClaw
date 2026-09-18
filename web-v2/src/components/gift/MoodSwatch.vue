<template>
  <svg
    class="mood"
    :viewBox="`0 0 ${w} ${h}`"
    preserveAspectRatio="xMidYMid slice"
    role="img"
    :aria-label="ariaLabel"
  >
    <!-- 底色取自色板最深的那个，保证任何色板下都有对比 -->
    <rect :width="w" :height="h" :fill="p[2]" />
    <!-- 三块柔和的几何构成本身就是「氛围」：叠圆 + 一条水平关系 -->
    <circle :cx="s.x1" :cy="s.y1" :r="s.r1" :fill="p[0]" :opacity="s.o1" />
    <circle :cx="s.x2" :cy="s.y2" :r="s.r2" :fill="p[1]" :opacity="s.o2" />
    <circle :cx="s.x3" :cy="s.y3" :r="s.r3" :fill="p[0]" :opacity="s.o3" />
    <rect :x="0" :y="h - s.base" :width="w" :height="s.base" :fill="p[2]" opacity="0.72" />
    <rect
      :x="s.bx" :y="h - s.base - 2" :width="s.bw" :height="2" rx="1"
      :fill="p[1]" opacity="0.6"
    />
  </svg>
</template>

<script setup>
/**
 * 氛围构成 —— 替代「氛围图片」的方案 A。
 *
 * 项目没有图片生成能力，也没有氛围图素材（public/ 只有 avatar / favicon / login-bg）。
 * 所以氛围不靠照片，靠「色板 + 几何构成」：纯 SVG、零请求、零素材，
 * 且因为颜色来自语义化的色板，天然适配浅色与深色两套主题
 * —— 真实照片反而要在两套主题下各自调色。
 *
 * 同一组 palette 必须渲染出同一个构成，所以位置由 seed 哈希决定，不用随机数。
 */
import { computed } from 'vue'

const props = defineProps({
  palette: { type: Array, default: () => ['#c9983c', '#dfc183', '#3a2f26'] },
  /** 决定构图；同一 seed 永远同一构图 */
  seed: { type: [String, Number], default: 'mood' },
  width: { type: Number, default: 320 },
  height: { type: Number, default: 120 },
  /** hero 用于展开卡主视觉，thumb 用于缩略图 */
  variant: { type: String, default: 'thumb' },
  label: { type: String, default: '' }
})

const w = computed(() => props.width)
const h = computed(() => props.height)

const p = computed(() => {
  const a = props.palette || []
  return [a[0] || '#c9983c', a[1] || '#dfc183', a[2] || '#3a2f26']
})

const ariaLabel = computed(() => props.label || '氛围构成')

const hash = (str) => {
  let v = 0
  const s = String(str)
  for (let i = 0; i < s.length; i++) {
    v = (v << 5) - v + s.charCodeAt(i)
    v |= 0
  }
  return Math.abs(v)
}

const s = computed(() => {
  const r = hash(props.seed)
  const pick = (range, offset) => ((r >> offset) % 1000) / 1000 * range
  const isHero = props.variant === 'hero'
  const unit = isHero ? 1 : 0.78 // 缩略图整体收敛一点，避免小尺寸下过碎

  return {
    x1: w.value * (0.16 + pick(0.18, 0)),
    y1: h.value * (0.3 + pick(0.35, 3)),
    r1: (h.value * (0.34 + pick(0.22, 6))) * unit,
    o1: 0.46,
    x2: w.value * (0.5 + pick(0.2, 9)),
    y2: h.value * (0.24 + pick(0.3, 12)),
    r2: (h.value * (0.26 + pick(0.18, 15))) * unit,
    o2: 0.3,
    x3: w.value * (0.74 + pick(0.18, 18)),
    y3: h.value * (0.4 + pick(0.3, 21)),
    r3: (h.value * (0.2 + pick(0.16, 24))) * unit,
    o3: 0.38,
    base: Math.max(10, h.value * 0.16),
    bx: w.value * 0.08,
    bw: w.value * (0.28 + pick(0.34, 27))
  }
})
</script>

<style lang="less" scoped>
.mood {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
