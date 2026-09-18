<template>
  <div class="gbox" role="img" :aria-label="ariaLabel">
    <div class="gbox__clip">
      <div class="gbox__face" :style="faceStyle" />
      <div class="gbox__lid" :style="lidStyle" />
      <span class="gbox__rv" :style="{ background: ribbonColor }" />
      <span class="gbox__rh" :style="{ background: ribbonColor }" />
    </div>

    <!-- 注意别在这里写静态 fill="none"：它会盖掉 :fill 绑定，蝴蝶结会变成空心线稿 -->
    <svg
      class="gbox__bow"
      viewBox="0 0 76 44"
      :stroke="ribbonColor"
      stroke-width="1.4"
      stroke-linejoin="round"
      aria-hidden="true"
    >
      <g :fill="ribbonColor">
        <path d="M38 23 C23 5 6 7 8 18 C10 28 27 28 38 23 Z" />
        <path d="M38 23 C53 5 70 7 68 18 C66 28 49 28 38 23 Z" />
        <circle cx="38" cy="23" r="4.6" />
      </g>
      <path d="M38 24 L30 40 M38 24 L46 40" fill="none" />
    </svg>
  </div>
</template>

<script setup>
/**
 * 礼盒 —— 页面上唯一的视觉主角。
 *
 * 盒面图案与丝带色都来自「零素材依赖」的方案 A：
 * 图案是 CSS 参数化生成（wrapPatternStyle），丝带是既有色板里的一个值，
 * 所以不引入任何图片、双主题下也都成立。
 *
 * 盒盖用同一图案叠一层压暗的底色（shade），而不是加阴影 ——
 * 纲领禁「无差别圆角 + 阴影堆叠」，礼盒的立体感靠分色做出。
 */
import { computed } from 'vue'
import { RIBBON_COLORS, wrapPatternStyle } from '@/data/giftDemo'

const props = defineProps({
  /** 方向的情境色板，取 [0] 作盒身、[1] 作图案线、[2] 作默认丝带 */
  palette: { type: Array, default: () => ['#c9983c', '#dfc183', '#3a2f26'] },
  wrap: { type: String, default: 'plain' },
  /**
   * 丝带色 id；'auto' 表示用色板最深色。
   * 必须这样兜底：默认的暖金 #c9983c 在「晚安治愈集」（盒身也是 #c9983c）
   * 里与盒身同色，丝带会整条消失。用色板最深色则任何方向下都有对比。
   */
  ribbon: { type: String, default: 'auto' },
  label: { type: String, default: '礼盒' }
})

const baseColor = computed(() => props.palette?.[0] || '#c9983c')

const ribbonColor = computed(() => {
  const fallback = props.palette?.[2] || '#3a2f26'
  if (!props.ribbon || props.ribbon === 'auto') return fallback
  const hit = RIBBON_COLORS.find((c) => c.id === props.ribbon)
  return hit ? hit.value : fallback
})

const pattern = computed(() => wrapPatternStyle(props.wrap, props.palette?.[1]))

/** 把 hex 按比例调亮/调暗并夹到 0–255；解析失败时原样返回，绝不产出非法颜色 */
const shade = (hex, k) => {
  const raw = String(hex).replace('#', '')
  const s = raw.length === 3 ? raw.split('').map((c) => c + c).join('') : raw
  if (!/^[0-9a-fA-F]{6}$/.test(s)) return hex
  const n = parseInt(s, 16)
  const cl = (v) => Math.max(0, Math.min(255, Math.round(v)))
  return `rgb(${cl(((n >> 16) & 255) * k)}, ${cl(((n >> 8) & 255) * k)}, ${cl((n & 255) * k)})`
}

const faceStyle = computed(() => ({ backgroundColor: baseColor.value, ...pattern.value }))

/** 盒盖：同图案 + 压暗底色，下沿用一条提亮线勾出盖沿，靠分色做出层次而不是阴影 */
const lidStyle = computed(() => ({
  backgroundColor: shade(baseColor.value, 0.74),
  borderBottomColor: shade(baseColor.value, 1.3),
  ...pattern.value
}))

const ariaLabel = computed(() => props.label)
</script>

<style lang="less" scoped>
.gbox {
  position: relative;
}

/* 圆角裁剪只作用于盒体，蝴蝶结留在外面，所以不能用 overflow 裁整个盒子 */
.gbox__clip {
  position: absolute;
  inset: 0;
  border-radius: 10px;
  overflow: hidden;
  border: 1px solid var(--border-strong);
}

.gbox__face { position: absolute; inset: 0; }

/* 盒盖：同图案 + 压暗底色，底边是一条提亮线 —— 盖沿靠分色而不是阴影。
   注意横丝带要压在盖缝【下方】，否则整条盖沿会被丝带盖掉，盒子就成了一块平板 */
.gbox__lid {
  position: absolute;
  left: 0;
  right: 0;
  top: 0;
  height: 32%;
  border-bottom: 1px solid;
}

.gbox__rv,
.gbox__rh {
  position: absolute;
  display: block;
}

/* 竖丝带 */
.gbox__rv {
  left: 50%;
  top: 0;
  bottom: 0;
  width: 18px;
  margin-left: -9px;
}

/* 横丝带：贴着盖沿下方系一圈 */
.gbox__rh {
  left: 0;
  right: 0;
  top: calc(32% + 5px);
  height: 18px;
}

.gbox__bow {
  position: absolute;
  left: 50%;
  top: -34px;
  width: 110px;
  height: 62px;
  transform: translateX(-50%);
}
</style>
