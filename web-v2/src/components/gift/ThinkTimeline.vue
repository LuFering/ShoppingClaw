<template>
  <div class="tl">
    <template v-for="g in groups" :key="g.key">
      <div class="tl__hd">
        <span class="tl__no mono">{{ g.no }}</span>
        <span class="tl__name">{{ g.label }}</span>
        <span class="tl__by mono">{{ g.by }}</span>
        <span class="tl__n mono">{{ g.items.length }}</span>
      </div>

      <ol class="tl__list">
        <li v-for="(e, k) in g.items" :key="k" class="tl__it">
          <span class="tl__tag" :class="tagClass(e)">{{ tagOf(e) }}</span>
          <div class="tl__body">
            <p v-if="e.kind === 'think' && e.by" class="tl__speaker">{{ e.by }}</p>
            <p class="tl__tx">{{ e.text }}</p>
          </div>
        </li>
      </ol>
    </template>

    <p v-if="!groups.length" class="tl__empty">还没有推理记录。</p>
  </div>
</template>

<script setup>
/**
 * 思考时间线 —— 推理可见性的第三层（覆盖层）。
 *
 * 这一层是唯一一个「可以长」的地方：它承载完整原文，用户想看才看、可回看。
 * 之所以能这样放开，是因为它不占页面高度 —— 主页面那一屏的约束与它无关。
 *
 * 按阶段分组而不是按时间平铺：agent 的推理是分段的，平铺会退化成日志流。
 */
import { computed } from 'vue'
import { STAGES } from '@/data/giftAgentStream'

const props = defineProps({
  timeline: { type: Array, default: () => [] }
})

const TAG = {
  think: '推理',
  evidence: '依据',
  direction: '提出方向',
  elements: '配构成',
  why: '为什么是它',
  risk: '风险',
  settle: '收束'
}

const tagOf = (e) => {
  if (e.kind === 'evidence') return e.label || '依据'
  if (e.kind === 'risk') return e.level === 'ok' ? '放心' : '警示'
  return TAG[e.kind] || e.kind
}

const tagClass = (e) => {
  if (e.kind === 'risk') return e.level === 'ok' ? 'is-ok' : 'is-warn'
  if (e.kind === 'think') return 'is-quiet'
  return ''
}

const groups = computed(() =>
  STAGES.map((s, i) => ({
    key: s.key,
    no: i + 1,
    label: s.label,
    by: s.by,
    items: props.timeline.filter((e) => e.stage === s.key)
  })).filter((g) => g.items.length)
)
</script>

<style lang="less" scoped>
.tl { max-width: 720px; }

.tl__hd {
  display: flex;
  align-items: baseline;
  gap: 9px;
  padding: 0 0 9px;
  margin-top: 22px;
  border-bottom: 1px solid var(--border);
}
.tl__hd:first-child { margin-top: 0; }
.tl__no { font-size: 0.72rem; color: var(--gift-accent); }
.tl__name {
  font-family: var(--font-display);
  font-size: 0.9rem;
  font-weight: 600;
  color: var(--text-strong);
}
.tl__by { font-size: 0.7rem; color: var(--text-faint); }
.tl__n { margin-left: auto; font-size: 0.7rem; color: var(--text-faint); }

.tl__list {
  list-style: none;
  margin: 0;
  padding: 0;
}
.tl__it {
  display: flex;
  gap: 11px;
  padding: 11px 0;
  border-bottom: 1px solid var(--border);
}
.tl__it:last-child { border-bottom: none; }

.tl__tag {
  flex: 0 0 auto;
  align-self: flex-start;
  font-size: 0.68rem;
  padding: 2px 8px;
  border-radius: 99px;
  border: 1px solid var(--gift-accent-line);
  color: var(--gift-accent);
  white-space: nowrap;
}
.tl__tag.is-quiet {
  border-color: var(--border);
  color: var(--text-faint);
}
.tl__tag.is-warn {
  border-color: var(--border-strong);
  color: var(--text-muted);
}
.tl__tag.is-ok {
  border-color: var(--border);
  color: var(--text-faint);
}

.tl__body { min-width: 0; }
.tl__speaker {
  font-size: 0.7rem;
  color: var(--gift-accent);
  margin: 0 0 3px;
}
.tl__tx {
  font-size: 0.8rem;
  line-height: 1.72;
  color: var(--text);
  margin: 0;
}

.tl__empty {
  font-size: 0.8rem;
  color: var(--text-faint);
  margin: 0;
}
</style>
