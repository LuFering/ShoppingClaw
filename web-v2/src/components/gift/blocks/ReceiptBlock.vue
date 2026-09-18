<template>
  <section class="gblock">
    <div class="g-step">
      <span class="g-step__no">⑤</span>
      <span class="g-step__t">这份心意，齐了</span>
      <span class="g-step__s">可保存 · 可分享 · 可直接下单</span>
    </div>

    <article class="gcard gcard--warm rc">
      <div class="rc__head">
        <div class="rc__mood">
          <MoodSwatch
            :palette="concept.palette"
            :seed="concept.id + '-rc'"
            variant="hero"
            :width="720"
            :height="120"
            :label="`${concept.title} 的氛围构成`"
          />
        </div>
        <div class="rc__meta">
          <p class="rc__to">
            给 <b>{{ brief.recipient || 'TA' }}</b> 的{{ brief.occasion || '心意' }}
          </p>
          <h2 class="rc__title">{{ concept.title }}</h2>
          <p class="rc__sub">{{ concept.thesis }}</p>
        </div>
      </div>

      <!-- 每件都带「为什么是它」：改过的用改动理由，没改的用原始说明 -->
      <ul class="rc__list">
        <li v-for="(el, i) in elements" :key="el.id" class="ri">
          <span class="ri__no mono">{{ ['①', '②', '③', '④'][i] || i + 1 }}</span>
          <div class="ri__b">
            <div class="ri__h">
              <span class="ri__n">{{ el.name }}</span>
              <span class="ri__p mono">{{ el.price ? '¥' + el.price : '含' }}</span>
            </div>
            <p class="ri__w">{{ el.reason || el.note }}</p>
          </div>
        </li>
      </ul>

      <!-- 寄语卡：用阶段 4 定下的排版与包装 -->
      <div class="rc__card-wrap" :style="wrapStyle">
        <div class="rc__ribbon" :style="{ background: ribbonValue }" />
        <div class="rc__card">
          <p class="rc__msg" :class="'st-' + custom.cardStyle">{{ custom.message }}</p>
        </div>
      </div>

      <div class="rc__sum">
        <span>合计</span>
        <span class="rc__total mono">¥{{ total }}</span>
      </div>

      <div class="rc__acts">
        <button class="gbtn gbtn--ghost" type="button" @click="copyText">
          {{ copied ? '已复制' : '复制文案' }}
        </button>
        <button class="gbtn" type="button" @click="$emit('save-image')">存成图片</button>
        <button class="gbtn gbtn--warm" type="button" @click="$emit('order')">去下单</button>
      </div>

      <p class="rc__foot">
        这份清单会同时存入购物档案 —— 下次给 <b>{{ brief.recipient || '同一个人' }}</b> 挑礼物时，我会记得这些偏好。
      </p>
    </article>
  </section>
</template>

<script setup>
/**
 * 阶段 5 · 礼品清单卷轴
 *
 * 不是订单详情页：它要能发给对方看「我准备了这些」，所以每件都必须带一句「为什么是它」。
 * 改过的物件用改动理由（用户自己的话），没改的用原始说明 —— 全程可追溯到来源。
 *
 * 落库：清单会写回购物档案（forWhom + scenario + 本次偏好观察）。
 * 这也是「收礼人档案」的来源 —— 不由用户手动维护，由每次送礼自动沉淀。
 */
import { ref, computed } from 'vue'
import MoodSwatch from '@/components/gift/MoodSwatch.vue'
import { wrapPatternStyle, RIBBON_COLORS } from '@/data/giftDemo'

const props = defineProps({
  brief: { type: Object, default: () => ({}) },
  concept: { type: Object, default: () => ({}) },
  elements: { type: Array, default: () => [] },
  custom: { type: Object, default: () => ({}) }
})

defineEmits(['save-image', 'order'])

const copied = ref(false)

const total = computed(() =>
  props.elements.reduce((s, e) => s + (Number(e.price) || 0), 0)
)

const wrapStyle = computed(() => wrapPatternStyle(props.custom.wrap, props.concept?.palette?.[1]))
const ribbonValue = computed(
  () => (RIBBON_COLORS.find((c) => c.id === props.custom.ribbon) || RIBBON_COLORS[0]).value
)

/** 复制成一段可以直接发出去的文案 */
const copyText = async () => {
  const lines = [
    `给${props.brief.recipient || 'TA'}的${props.brief.occasion || '心意'} · ${props.concept?.title || ''}`,
    '',
    ...props.elements.map((e) => `· ${e.name}${e.price ? `（¥${e.price}）` : ''} —— ${e.reason || e.note}`),
    '',
    props.custom?.message || '',
    '',
    `合计 ¥${total.value}`
  ]
  const text = lines.join('\n')
  const done = () => {
    copied.value = true
    setTimeout(() => { copied.value = false }, 1800)
  }

  // navigator.clipboard 只在安全上下文（https 或 localhost）存在。
  // 线上是 http://<IP>，它不可用，所以必须有 execCommand 兜底，
  // 否则这个按钮在真实环境里是坏的（本地开发反而测不出来）。
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(text)
      done()
      return
    } catch {
      /* 权限被拒时落到兜底 */
    }
  }

  const ta = document.createElement('textarea')
  ta.value = text
  ta.setAttribute('readonly', '')
  ta.style.position = 'fixed'
  ta.style.top = '-1000px'
  ta.style.opacity = '0'
  document.body.appendChild(ta)
  ta.select()
  let ok = false
  try {
    ok = document.execCommand('copy')
  } catch {
    ok = false
  }
  document.body.removeChild(ta)
  if (ok) done()
}
</script>

<style lang="less" scoped>
.rc { padding: 0; }

.rc__head { position: relative; }
.rc__mood { height: 120px; }
.rc__meta { padding: 15px 20px 16px; }
.rc__to {
  font-size: 0.76rem;
  color: var(--text-muted);
  margin: 0 0 6px;
}
.rc__to b { color: var(--text-strong); font-weight: 600; }
.rc__title {
  font-family: var(--font-display);
  font-size: 1.06rem;
  font-weight: 600;
  color: var(--text-strong);
  margin: 0 0 6px;
}
.rc__sub {
  font-size: 0.78rem;
  line-height: 1.65;
  color: var(--text-muted);
  margin: 0;
}

.rc__list {
  list-style: none;
  margin: 0;
  padding: 0;
  border-top: 1px solid var(--border);
}
.ri {
  display: flex;
  gap: 11px;
  padding: 12px 20px;
  border-bottom: 1px solid var(--border);
}
.ri__no { font-size: 0.72rem; color: var(--text-faint); flex: 0 0 auto; padding-top: 2px; }
.ri__b { flex: 1; min-width: 0; }
.ri__h { display: flex; align-items: baseline; gap: 9px; }
.ri__n { font-size: 0.85rem; font-weight: 600; color: var(--text-strong); }
.ri__p { margin-left: auto; font-size: 0.78rem; color: var(--text-muted); flex: 0 0 auto; }
.ri__w {
  font-size: 0.73rem;
  line-height: 1.6;
  color: var(--text-muted);
  margin: 4px 0 0;
}

/* 寄语卡 */
.rc__card-wrap {
  position: relative;
  margin: 18px 20px;
  border-radius: 11px;
  border: 1px solid var(--border);
  overflow: hidden;
  padding: 22px 20px 26px;
  background-color: var(--gift-accent-soft);
}
.rc__ribbon {
  position: absolute;
  left: 0;
  right: 0;
  top: 40%;
  height: 12px;
  opacity: 0.9;
}
.rc__card {
  position: relative;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 9px;
  padding: 18px 20px;
}
.rc__msg { margin: 0; white-space: pre-wrap; color: var(--text); }

.st-plain { font-family: var(--font-body); font-size: 0.86rem; line-height: 1.8; }
.st-soft {
  font-family: var(--font-body); font-size: 0.81rem; line-height: 2.1;
  letter-spacing: 0.02em; color: var(--text-muted);
}
.st-formal {
  font-family: var(--font-display); font-size: 0.84rem; line-height: 1.9;
  letter-spacing: 0.05em; text-align: center;
}

.rc__sum {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  padding: 14px 20px;
  border-top: 1px solid var(--border);
  font-size: 0.82rem;
  color: var(--text-muted);
}
.rc__total { font-size: 1.16rem; font-weight: 600; color: var(--text-strong); }

.rc__acts {
  display: flex;
  gap: 9px;
  padding: 0 20px 16px;
  flex-wrap: wrap;
}
.rc__acts .gbtn { flex: 1; min-width: 108px; }

.rc__foot {
  padding: 12px 20px 16px;
  border-top: 1px solid var(--border);
  background: var(--bg-sunken);
  font-size: 0.72rem;
  line-height: 1.6;
  color: var(--text-faint);
  margin: 0;
}
.rc__foot b { color: var(--text-muted); font-weight: 600; }
</style>
