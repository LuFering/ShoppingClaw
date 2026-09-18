<template>
  <svg
    class="glyph"
    viewBox="0 0 48 48"
    fill="none"
    :stroke="color"
    stroke-width="1.6"
    stroke-linejoin="round"
    stroke-linecap="round"
    role="img"
    :aria-label="ariaLabel"
  >
    <template v-if="kind === 'candle'">
      <rect x="18" y="21" width="12" height="19" rx="2" />
      <ellipse cx="24" cy="21" rx="6" ry="2.2" />
      <line x1="24" y1="17" x2="24" y2="20" />
      <path d="M24 8 C26.8 11.4 26.8 14.4 24 16.8 C21.2 14.4 21.2 11.4 24 8 Z" />
    </template>

    <template v-else-if="kind === 'cup'">
      <rect x="12" y="12" width="24" height="6" rx="2" />
      <rect x="20" y="6" width="8" height="6" rx="2" />
      <path d="M15 18 L17.2 38 Q17.4 41 20.2 41 L27.8 41 Q30.6 41 30.8 38 L33 18" />
      <path d="M33.4 23 Q40.5 23 40.5 30 Q40.5 36 33.4 35" />
    </template>

    <template v-else-if="kind === 'card'">
      <rect x="13" y="8" width="22" height="32" rx="2.5" />
      <path d="M18 16 H30 M18 22 H30 M18 28 H25" />
    </template>

    <template v-else-if="kind === 'soap'">
      <rect x="10" y="17" width="28" height="17" rx="6" />
      <path d="M17 24 Q24 20.5 31 24" />
    </template>

    <template v-else-if="kind === 'pendant'">
      <path d="M24 6 V13" />
      <circle cx="24" cy="27" r="10" />
      <path d="M19.5 27 Q24 32.5 28.5 27" />
    </template>

    <template v-else-if="kind === 'ticket'">
      <rect x="9" y="15" width="30" height="19" rx="3" />
      <path d="M27 15 V34" stroke-dasharray="3 3" />
      <path d="M15 22 H22 M15 28 H22" />
    </template>

    <template v-else-if="kind === 'scarf'">
      <path d="M15 12 H33 Q36 12 36 15 V20 Q36 23 33 23 H15 Q12 23 12 20 V15 Q12 12 15 12 Z" />
      <path d="M18 23 V36 M30 23 V36" />
      <path d="M15 36 H21 M27 36 H33" />
    </template>

    <template v-else-if="kind === 'glove'">
      <path d="M17 23 V13 Q17 9 21.5 9 Q26 9 26 13 V23" />
      <path d="M14 23 H31 Q34 23 34 26 V32 Q34 41 24 41 Q14 41 14 32 V26 Q14 23 17 23 Z" />
      <path d="M16 29 H32" />
    </template>

    <template v-else-if="kind === 'device'">
      <rect x="13" y="15" width="22" height="22" rx="7" />
      <path d="M18 26 q3 -4.5 6 0 q3 4.5 6 0" />
    </template>

    <template v-else-if="kind === 'soft'">
      <path d="M12 20 Q24 11 36 20 L36 30 Q24 39 12 30 Z" />
      <path d="M12 25 Q24 34 36 25" opacity="0.45" />
    </template>

    <template v-else-if="kind === 'plant'">
      <path d="M17 27 H31 L29.5 41 H18.5 Z" />
      <path d="M24 27 V14" />
      <path d="M24 19 Q17.5 17 15.5 10.5 Q22 10 24 16" />
      <path d="M24 19 Q30.5 17 32.5 10.5 Q26 10 24 16" />
    </template>

    <template v-else>
      <rect x="11" y="14" width="26" height="21" rx="4" />
      <circle cx="24" cy="24.5" r="3.2" />
    </template>
  </svg>
</template>

<script setup>
/**
 * 物件剪影 —— 替代「氛围色块」当缩略图。
 *
 * 上一版物件用的是 MoodSwatch（色板+几何），在卡片里看起来像「图片没加载出来」，
 * 这是用户说「视觉不好看」的主要来源之一。物件要能被认出来，所以这里画的是轮廓。
 *
 * 不依赖任何图标库：本项目没有图标依赖，且需要跟色板同色（用 stroke=currentColor 之外的显式色）。
 * 形状由 role 关键词决定；没命中就用中性形状兜底，不会出现空框。
 */
import { computed } from 'vue'

const props = defineProps({
  /** 物件的角色名，如「香薰蜡烛」「安睡茶饮」 */
  role: { type: String, default: '' },
  color: { type: String, default: 'var(--gift-accent)' },
  label: { type: String, default: '' }
})

/* 顺序有讲究：
   1. 「香薰加湿器」会同时命中 /香薰/，所以小家电必须先判
   2. 围巾与手套要分开 —— 上一版都落到同一个形状，三件里有两件长得一样 */
const RULES = [
  [/加湿器|暖手宝|小家电|按摩|电器/, 'device'],
  [/围巾|披肩/, 'scarf'],
  [/手套/, 'glove'],
  [/靠垫|腰靠|抱枕/, 'soft'],
  [/蜡烛|扩香|香薰|藤条|精油/, 'candle'],
  [/茶|杯|饮|可可|牛奶/, 'cup'],
  [/卡片|邀请卡|相册|贺卡|记录/, 'card'],
  [/皂|护手霜/, 'soap'],
  [/挂件|摆件/, 'pendant'],
  [/体验|课/, 'ticket'],
  [/绿植|植物/, 'plant']
]

const kind = computed(() => {
  const s = String(props.role || '')
  for (const [re, k] of RULES) if (re.test(s)) return k
  return 'generic'
})

const ariaLabel = computed(() => props.label || `${props.role || '物件'} 示意`)
</script>

<style lang="less" scoped>
.glyph {
  display: block;
  width: 100%;
  height: 100%;
}
</style>
