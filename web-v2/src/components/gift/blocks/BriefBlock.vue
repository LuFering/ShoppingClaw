<template>
  <section class="gblock brief">
    <div class="brief__mark">礼</div>

    <h1 class="brief__title">我想替你挑一件，能被记住的</h1>
    <p class="brief__sub">先告诉我给谁、什么日子、大概多少 —— 不用想怎么跟我说话</p>

    <!-- 填空式开场：两个内联下拉 + 一条滑轨，替代空白聊天框 -->
    <div class="gcard gcard--warm brief__card">
      <p class="sent">
        我想给
        <span class="slot">
          <select v-model="recipient" class="slot__sel" aria-label="送给谁">
            <option v-for="r in recipients" :key="r" :value="r">{{ r }}</option>
          </select>
          <span class="slot__car">▾</span>
        </span>
        准备一份
        <span class="slot">
          <select v-model="occasion" class="slot__sel" aria-label="什么场合">
            <option v-for="o in occasions" :key="o" :value="o">{{ o }}</option>
          </select>
          <span class="slot__car">▾</span>
        </span>
        礼物
      </p>

      <div class="budget">
        <span class="budget__k">预算大概</span>
        <input
          v-model.number="budget"
          class="budget__range"
          type="range"
          min="200"
          max="3000"
          step="50"
          aria-label="预算"
        />
        <span class="budget__v mono">¥{{ budget.toLocaleString('en-US') }}</span>
      </div>

      <button class="gbtn gbtn--warm brief__go" type="button" @click="submit">
        看看有什么灵感
      </button>
    </div>

    <!-- 从购物档案沉底下来的收礼人：不由用户手动维护，是上次送礼自动留下的 -->
    <div v-if="known.length" class="brief__known">
      <p class="g-label">还记得这几位</p>
      <div class="brief__chips">
        <button
          v-for="k in known"
          :key="k.id"
          class="kchip"
          :class="{ on: picked === k.id }"
          type="button"
          @click="pickKnown(k)"
        >
          <span class="kchip__n">{{ k.name }}</span>
          <span class="kchip__d">{{ k.relation }} · 上次送「{{ k.lastGift }}」{{ k.lastFeedback }}</span>
        </button>
      </div>
    </div>
  </section>
</template>

<script setup>
/**
 * 阶段 1 · 情境开场
 *
 * 刻意不做一个空白聊天框：用户面对空输入框要想「我该怎么说」，
 * 而填空句只要求他在三个位置上各做一个轻决定。
 *
 * 预算用滑轨而不是输入框：滑轨给出的是心理区间，输入框要求精确 ——
 * 而"还没想好具体多少"才是这个场景的真实状态。
 */
import { ref, computed } from 'vue'
import { RECIPIENT_OPTIONS, OCCASION_OPTIONS, KNOWN_RECIPIENTS } from '@/data/giftDemo'

const emit = defineEmits(['submit'])

const recipients = RECIPIENT_OPTIONS
const occasions = OCCASION_OPTIONS
const known = computed(() => KNOWN_RECIPIENTS)

const recipient = ref('女朋友')
const occasion = ref('生日')
const budget = ref(800)
const picked = ref('')

const pickKnown = (k) => {
  picked.value = picked.value === k.id ? '' : k.id
  if (picked.value) recipient.value = k.name
}

const submit = () => {
  emit('submit', {
    recipient: recipient.value,
    occasion: occasion.value,
    budget: budget.value,
    knownRecipientId: picked.value || null
  })
}
</script>

<style lang="less" scoped>
.brief {
  text-align: center;
  padding-top: 12px;
}

.brief__mark {
  width: 46px;
  height: 46px;
  border-radius: 13px;
  margin: 0 auto 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--gift-accent-soft);
  color: var(--gift-accent);
  font-size: 1rem;
  font-weight: 600;
}

.brief__title {
  font-family: var(--font-display);
  font-size: 1.3rem;
  font-weight: 600;
  color: var(--text-strong);
  margin: 0;
  line-height: 1.4;
}

.brief__sub {
  font-size: 0.84rem;
  color: var(--text-muted);
  margin: 9px 0 22px;
}

.brief__card {
  padding: 26px 24px 24px;
  text-align: left;
}

/* 填空句 */
.sent {
  font-size: 1.06rem;
  line-height: 2.1;
  color: var(--text);
  margin: 0 0 20px;
}
.slot {
  position: relative;
  display: inline-flex;
  align-items: center;
  margin: 0 3px;
  border-bottom: 1px dashed var(--gift-accent);
  vertical-align: baseline;
}
.slot__sel {
  appearance: none;
  -webkit-appearance: none;
  border: none;
  outline: none;
  background: transparent;
  font-family: var(--font-body);
  font-size: 1.06rem;
  line-height: 1.8;
  color: var(--gift-accent);
  padding: 0 18px 0 4px;
  cursor: pointer;
  font-weight: 500;
}
.slot__sel option { color: var(--text); background: var(--bg-surface); }
.slot__car {
  position: absolute;
  right: 3px;
  font-size: 0.66rem;
  color: var(--gift-accent);
  pointer-events: none;
  opacity: 0.75;
}

/* 预算滑轨 */
.budget {
  display: flex;
  align-items: center;
  gap: 14px;
  margin-bottom: 22px;
}
.budget__k { font-size: 1.06rem; color: var(--text); white-space: nowrap; }
.budget__v {
  font-size: 1rem;
  font-weight: 600;
  color: var(--gift-accent);
  min-width: 66px;
  text-align: right;
}
.budget__range {
  flex: 1;
  min-width: 0;
  appearance: none;
  -webkit-appearance: none;
  height: 4px;
  border-radius: 2px;
  background: var(--border-strong);
  outline: none;
  cursor: pointer;
}
.budget__range::-webkit-slider-thumb {
  appearance: none;
  -webkit-appearance: none;
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--gift-accent);
  border: 2px solid var(--bg-surface);
  cursor: pointer;
}
.budget__range::-moz-range-thumb {
  width: 16px;
  height: 16px;
  border-radius: 50%;
  background: var(--gift-accent);
  border: 2px solid var(--bg-surface);
  cursor: pointer;
}

.brief__go { width: 100%; padding: 11px 18px; font-size: 0.86rem; }

/* 已沉淀的收礼人 */
.brief__known {
  margin-top: 22px;
  text-align: left;
}
.brief__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 9px;
}
.kchip {
  text-align: left;
  font-family: var(--font-body);
  padding: 8px 13px;
  border-radius: 9px;
  border: 1px solid var(--border);
  background: var(--bg-surface);
  cursor: pointer;
  transition: border-color 0.15s ease-out;
}
.kchip:hover { border-color: var(--border-strong); }
.kchip.on { border-color: var(--gift-accent); background: var(--gift-accent-soft); }
.kchip__n {
  display: block;
  font-size: 0.82rem;
  font-weight: 500;
  color: var(--text-strong);
}
.kchip__d {
  display: block;
  font-size: 0.71rem;
  color: var(--text-muted);
  margin-top: 2px;
}
</style>
