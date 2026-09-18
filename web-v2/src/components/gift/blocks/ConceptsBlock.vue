<template>
  <section class="gblock">
    <div class="g-step">
      <span class="g-step__no">②</span>
      <span class="g-step__t">我想到 {{ list.length }} 个方向</span>
      <span class="g-step__s">都是组合，不是单个商品</span>
    </div>

    <div class="grid">
      <article
        v-for="c in list"
        :key="c.id"
        class="cc"
        :class="{ on: selectedId === c.id }"
      >
        <div class="cc__mood">
          <MoodSwatch
            :palette="c.palette"
            :seed="c.id"
            variant="thumb"
            :width="320"
            :height="104"
            :label="`${c.title} 的氛围构成`"
          />
          <span class="cc__moodlab">{{ c.moodLabel }}</span>
        </div>

        <div class="cc__body">
          <h3 class="cc__title">{{ c.title }}</h3>
          <p class="cc__thesis">{{ c.thesis }}</p>

          <ul class="cc__parts">
            <li v-for="e in (c.elements || []).slice(0, 3)" :key="e.id">
              <span class="cc__dot" />{{ e.role }}
            </li>
          </ul>

          <div class="cc__foot">
            <span class="cc__price mono">¥{{ totalOf(c) }}</span>
            <span class="cc__note">{{ c.budgetNote }}</span>
          </div>

          <button class="gbtn cc__cta" type="button" @click="$emit('pick', c)">
            {{ selectedId === c.id ? '已选，往下看' : '进一步探讨这个方向' }}
          </button>
        </div>
      </article>
    </div>

    <div class="refresh">
      <button class="gbtn" type="button" @click="$emit('refresh')">↻ 换一批灵感</button>
    </div>
  </section>
</template>

<script setup>
/**
 * 阶段 2 · 概念提案
 *
 * 卡片之间必须是「方向差异」，不是同一方向的三个价位 ——
 * 「晚安治愈集 / 手作温度盒 / 一起去做的事」三者的送礼逻辑完全不同。
 *
 * 每张卡必含四样（这是豁免「更大留白」的对价，见 gift.less 的说明）：
 *   氛围构成 · 概念解释 · 构成预览 · 预计总价
 */
import MoodSwatch from '@/components/gift/MoodSwatch.vue'
import { totalOf } from '@/data/giftDemo'

defineProps({
  list: { type: Array, default: () => [] },
  selectedId: { type: String, default: '' }
})

defineEmits(['pick', 'refresh'])
</script>

<style lang="less" scoped>
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(208px, 1fr));
  gap: 14px;
}

.cc {
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
  background: var(--bg-surface);
  display: flex;
  flex-direction: column;
  transition: border-color 0.16s ease-out;
}
.cc:hover { border-color: var(--border-strong); }
.cc.on { border-color: var(--gift-accent); }

.cc__mood {
  position: relative;
  height: 104px;
}
.cc__moodlab {
  position: absolute;
  left: 10px;
  bottom: 8px;
  font-size: 0.68rem;
  color: #f3f5f4;
  background: rgba(0, 0, 0, 0.34);
  padding: 2px 8px;
  border-radius: 99px;
}

.cc__body {
  padding: 13px 14px 15px;
  display: flex;
  flex-direction: column;
  flex: 1;
}
.cc__title {
  font-family: var(--font-display);
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--text-strong);
  margin: 0 0 6px;
}
.cc__thesis {
  font-size: 0.76rem;
  line-height: 1.62;
  color: var(--text-muted);
  margin: 0 0 10px;
}

.cc__parts {
  list-style: none;
  margin: 0 0 12px;
  padding: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 4px 10px;
}
.cc__parts li {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 0.72rem;
  color: var(--text-muted);
}
.cc__dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: var(--gift-accent);
  flex: 0 0 auto;
}

.cc__foot {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin-top: auto;
  padding-bottom: 12px;
}
.cc__price {
  font-size: 0.92rem;
  font-weight: 600;
  color: var(--text-strong);
}
.cc__note { font-size: 0.7rem; color: var(--text-faint); }

.cc__cta { width: 100%; font-size: 0.76rem; padding: 7px 12px; }

.refresh {
  text-align: center;
  margin-top: 16px;
}
</style>
