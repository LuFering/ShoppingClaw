<template>
  <section class="gblock">
    <div class="g-step">
      <span class="g-step__no">④</span>
      <span class="g-step__t">把心意落到纸和包装上</span>
      <span class="g-step__s">寄语是从你前面的改动里长出来的</span>
    </div>

    <div class="gcard gcard--warm ws" :class="{ 'ws--fs': fullscreen }">
      <div class="ws__bar">
        <span class="ws__bart">定制工作台</span>
        <button class="gbtn ws__fsbtn" type="button" @click="fullscreen = !fullscreen">
          {{ fullscreen ? '退出全屏' : '全屏制作' }}
        </button>
      </div>

      <div class="ws__body">
        <!-- 预览：包装底 + 丝带 + 贺卡，改什么立刻看到 -->
        <div class="pv" :style="wrapStyle">
          <div class="pv__ribbon" :style="{ background: ribbonValue }" />
          <div class="pv__card">
            <p class="pv__msg" :class="'st-' + cardStyle">{{ message }}</p>
          </div>
        </div>

        <!-- 寄语 -->
        <div class="ws__sec">
          <div class="ws__sech">
            <span class="g-label">贺卡寄语</span>
            <span class="ws__sechint">可以直接改</span>
          </div>
          <textarea v-model="message" class="ws__ta" rows="6" aria-label="贺卡寄语" />
          <div class="ws__styles">
            <button
              v-for="s in CARD_STYLES"
              :key="s.id"
              class="stab"
              :class="{ on: cardStyle === s.id }"
              type="button"
              @click="cardStyle = s.id"
            >
              <span class="stab__n" :class="'st-' + s.id">样式</span>
              <span class="stab__l">{{ s.label }}</span>
              <span class="stab__d">{{ s.note }}</span>
            </button>
          </div>
        </div>

        <!-- 包装 -->
        <div class="ws__sec">
          <div class="ws__sech">
            <span class="g-label">包装纸</span>
            <span class="ws__sechint">图案用 CSS 生成，不需要素材</span>
          </div>
          <div class="ws__row">
            <button
              v-for="p in WRAP_PATTERNS"
              :key="p.id"
              class="pbtn"
              :class="{ on: wrap === p.id }"
              type="button"
              @click="wrap = p.id"
            >
              <span class="pbtn__sw" :style="wrapPatternStyle(p.id, concept.palette[1])" />
              <span class="pbtn__l">{{ p.label }}</span>
            </button>
          </div>

          <div class="ws__sech" style="margin-top:16px">
            <span class="g-label">丝带</span>
          </div>
          <div class="ws__row">
            <button
              v-for="c in RIBBON_COLORS"
              :key="c.id"
              class="cbtn"
              :class="{ on: ribbon === c.id }"
              type="button"
              :aria-label="c.label"
              @click="ribbon = c.id"
            >
              <span class="cbtn__sw" :style="{ background: c.value }" />
              <span class="cbtn__l">{{ c.label }}</span>
            </button>
          </div>
        </div>
      </div>

      <div class="ws__foot">
        <button class="gbtn gbtn--warm" type="button" @click="finish">就这样，看清单</button>
      </div>
    </div>

    <!-- 全屏时把背景压暗，卷轴仍在下面原位 -->
    <div v-if="fullscreen" class="ws__scrim" @click="fullscreen = false" />
  </section>
</template>

<script setup>
/**
 * 阶段 4 · 定制工作台
 *
 * 全屏不是新页面，而是在原块上放大并把背景压暗 —— 退出后回到卷轴原位，滚动位置不变。
 *
 * 寄语不是让 agent 凭空写一段祝福，而是由阶段 3 累积的「改动理由」拼装：
 * 用户说过「能换成热饮吗」，寄语里就会出现这一句的回应。
 * 这样寄语才是「这一份礼物」的，而不是任何一份礼物都能用的模板。
 *
 * 三套排版风格用现有字体做差异（不引入字体资源）：
 * 字体族 + 字号 + 行高 + 字距 + 对齐，四者组合足以看出区别。
 */
import { ref, computed } from 'vue'
import {
  CARD_STYLES,
  WRAP_PATTERNS,
  RIBBON_COLORS,
  wrapPatternStyle,
  buildMessage
} from '@/data/giftDemo'

const props = defineProps({
  recipient: { type: String, default: '' },
  occasion: { type: String, default: '' },
  concept: { type: Object, default: () => ({}) },
  revisions: { type: Array, default: () => [] }
})

const emit = defineEmits(['done'])

const fullscreen = ref(false)
const cardStyle = ref('soft')
const wrap = ref('stripe')
const ribbon = ref('gold')

const message = ref(
  buildMessage({
    recipient: props.recipient,
    occasion: props.occasion,
    concept: props.concept,
    revisions: props.revisions
  })
)

const wrapStyle = computed(() => wrapPatternStyle(wrap.value, props.concept?.palette?.[1]))
const ribbonValue = computed(
  () => (RIBBON_COLORS.find((c) => c.id === ribbon.value) || RIBBON_COLORS[0]).value
)

const finish = () => {
  emit('done', {
    message: message.value,
    cardStyle: cardStyle.value,
    wrap: wrap.value,
    ribbon: ribbon.value
  })
}
</script>

<style lang="less" scoped>
.ws { padding: 0; }

.ws__bar {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 11px 18px;
  border-bottom: 1px solid var(--border);
}
.ws__bart { font-size: 0.78rem; font-weight: 600; color: var(--text-strong); }
.ws__fsbtn { margin-left: auto; font-size: 0.72rem; padding: 4px 12px; }

.ws__body { padding: 18px; }

/* 预览 */
.pv {
  position: relative;
  border-radius: 12px;
  border: 1px solid var(--border);
  overflow: hidden;
  padding: 26px 24px 30px;
  background-color: var(--gift-accent-soft);
  transition: background-color 0.2s ease-out;
}
.pv__ribbon {
  position: absolute;
  left: 0;
  right: 0;
  top: 42%;
  height: 14px;
  opacity: 0.9;
}
.pv__card {
  position: relative;
  background: var(--bg-surface);
  border-radius: 10px;
  border: 1px solid var(--border);
  padding: 20px 22px;
  max-width: 460px;
  margin: 0 auto;
}
.pv__msg {
  margin: 0;
  white-space: pre-wrap;
  color: var(--text);
}

/* 三套排版风格：字体族 + 字号 + 行高 + 字距 + 对齐 */
.st-plain {
  font-family: var(--font-body);
  font-size: 0.86rem;
  line-height: 1.8;
  letter-spacing: 0;
}
.st-soft {
  font-family: var(--font-body);
  font-size: 0.81rem;
  line-height: 2.1;
  letter-spacing: 0.02em;
  color: var(--text-muted);
}
.st-formal {
  font-family: var(--font-display);
  font-size: 0.84rem;
  line-height: 1.9;
  letter-spacing: 0.05em;
  text-align: center;
}

/* 寄语 */
.ws__sec { margin-top: 20px; }
.ws__sech {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 9px;
}
.ws__sechint { margin-left: auto; font-size: 0.7rem; color: var(--text-faint); }
.ws__ta {
  width: 100%;
  padding: 12px 14px;
  border: 1px solid var(--border-strong);
  border-radius: 9px;
  background: var(--bg-surface);
  color: var(--text);
  font-family: var(--font-body);
  font-size: 0.82rem;
  line-height: 1.85;
  resize: vertical;
  outline: none;
}
.ws__ta:focus { border-color: var(--gift-accent); }

.ws__styles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(132px, 1fr));
  gap: 9px;
  margin-top: 11px;
}
.stab {
  display: flex;
  flex-direction: column;
  gap: 3px;
  text-align: left;
  font-family: var(--font-body);
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-surface);
  cursor: pointer;
  transition: border-color 0.15s ease-out;
}
.stab:hover { border-color: var(--border-strong); }
.stab.on { border-color: var(--gift-accent); }
.stab__n { font-size: 0.9rem; color: var(--text-strong); line-height: 1.3; }
.stab__l { font-size: 0.78rem; font-weight: 500; color: var(--text-strong); }
.stab__d { font-size: 0.68rem; color: var(--text-faint); }

/* 包装 */
.ws__row { display: flex; flex-wrap: wrap; gap: 9px; }
.pbtn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  padding: 8px;
  border: 1px solid var(--border);
  border-radius: 9px;
  background: var(--bg-surface);
  cursor: pointer;
  transition: border-color 0.15s ease-out;
}
.pbtn:hover { border-color: var(--border-strong); }
.pbtn.on { border-color: var(--gift-accent); }
.pbtn__sw {
  width: 46px;
  height: 30px;
  border-radius: 5px;
  border: 1px solid var(--border);
  background-color: var(--gift-accent-soft);
}
.pbtn__l { font-size: 0.7rem; color: var(--text-muted); font-family: var(--font-body); }

.cbtn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  border: 1px solid var(--border);
  border-radius: 99px;
  background: var(--bg-surface);
  cursor: pointer;
  font-family: var(--font-body);
  transition: border-color 0.15s ease-out;
}
.cbtn:hover { border-color: var(--border-strong); }
.cbtn.on { border-color: var(--gift-accent); }
.cbtn__sw { width: 13px; height: 13px; border-radius: 50%; display: block; }
.cbtn__l { font-size: 0.72rem; color: var(--text-muted); }

.ws__foot {
  display: flex;
  justify-content: flex-end;
  padding: 14px 18px 18px;
  border-top: 1px solid var(--border);
}

/* 全屏：原块放大，背景压暗；退出后回到原位 */
.ws--fs {
  position: fixed;
  inset: 4vh 5vw;
  z-index: 60;
  overflow-y: auto;
  background: var(--bg-surface);
}
.ws__scrim {
  position: fixed;
  inset: 0;
  z-index: 50;
  background: var(--bg-overlay);
}
</style>
