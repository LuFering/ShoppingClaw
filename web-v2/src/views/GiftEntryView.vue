<template>
  <div class="page">
    <PageHeader
      title="代购送礼"
      desc="读收礼人的真实偏好，组合成一份每处取舍都说得清的礼物"
    >
      <template #mark>礼</template>
      <template #stats>
        <span class="stat-pill">进行中 <b>{{ runningCount }}</b> 个</span>
      </template>
      <template #actions>
        <a-button size="small" class="lucide-icon-btn" @click="router.push('/decisions')">
          <Library :size="14" /><span>购物档案</span>
        </a-button>
      </template>
    </PageHeader>

    <div class="gf-grid">
      <!-- 左：这次送礼的情境 -->
      <section class="page-section">
        <div class="page-section-head">
          <h2 class="page-section-title">告诉我这一次</h2>
          <span class="page-section-desc">不需要一次说完，之后可以在方案上批注</span>
        </div>

        <div class="gf-form">
          <label class="gf-field">
            <span class="gf-label">送给谁</span>
            <select v-model="draft.recipient" class="gf-select">
              <option v-for="r in RECIPIENTS" :key="r" :value="r">{{ r }}</option>
            </select>
          </label>

          <label class="gf-field">
            <span class="gf-label">为了什么</span>
            <select v-model="draft.occasion" class="gf-select">
              <option v-for="o in OCCASIONS" :key="o" :value="o">{{ o }}</option>
            </select>
          </label>

          <div class="gf-field">
            <div class="gf-label-row">
              <span class="gf-label">预算大概</span>
              <strong class="mono">¥{{ draft.budget }}</strong>
            </div>
            <input
              v-model.number="draft.budget"
              class="gf-range"
              type="range" min="200" max="3000" step="50"
              aria-label="预算"
            />
            <div class="gf-range-labels mono">
              <span>¥200</span><span>更看重心意</span><span>¥3,000</span>
            </div>
          </div>

          <div class="gf-field">
            <span class="gf-label">你更在意哪一件事</span>
            <div class="gf-signals">
              <button
                v-for="s in SIGNALS"
                :key="s.label"
                class="gf-signal"
                :class="{ on: draft.signals.includes(s.label) }"
                type="button"
                @click="toggleSignal(s.label)"
              >
                <i>{{ s.mark }}</i>
                <span>{{ s.label }}</span>
                <em>{{ s.detail }}</em>
              </button>
            </div>
          </div>

          <button class="gf-submit" type="button" :disabled="submitting" @click="begin">
            {{ submitting ? '正在开始…' : '开始挑这份礼物 →' }}
          </button>
          <p v-if="submitError" class="gf-err">{{ submitError }}</p>
        </div>
      </section>

      <!-- 右：说明这是怎么工作的 -->
      <aside class="page-section">
        <div class="page-section-head">
          <h2 class="page-section-title">推演步骤</h2>
        </div>
        <ol class="gf-steps">
          <li v-for="(s, i) in PROCESS" :key="s.name">
            <span class="gf-step-no mono">{{ i + 1 }}</span>
            <div>
              <p class="gf-step-name">{{ s.name }}</p>
              <p class="gf-step-detail">{{ s.detail }}</p>
            </div>
          </li>
        </ol>
        <p class="gf-note">
          每一步的关键依据都会留在工作台上，可核对，也可改。
        </p>
      </aside>
    </div>
  </div>
</template>

<script setup>
/**
 * 送礼智能体 · 入口页
 *
 * 职责是「收敛意图」：把送礼情境（送谁 / 场合 / 预算 / 在意什么）
 * 收敛成结构化参数，然后建一个真实的 run 交给工作台。
 *
 * 2026-09-24：原先 `/proxy` 直接是工作台，开局用的是写死的 mock TASK ——
 * 用户没有地方描述「这次是送给谁」。本页补上这个入口。
 *
 * 布局沿用全站约定（.page + PageHeader），与 /planning、/tasks 同一阅读起点。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Library } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import { giftApi } from '@/apis/gift_api'

const router = useRouter()

const RECIPIENTS = ['妈妈', '爸爸', '伴侣', '朋友', '同事', '长辈']
const OCCASIONS = ['生日', '纪念日', '节日', '道谢', '探望', '没有特别理由']

// signals 的 label 会**原样发给后端**：后端按标签查品类映射表
// （见 stages.SIGNAL_TO_GOODS）。所以这里的 label 不能用内部 key，
// 必须是可读中文 —— 后端也认这套说法。
const SIGNALS = [
  { mark: '用', label: '真的用得上', detail: '少一点闲置，多一点日常陪伴' },
  { mark: '心', label: '看得出花了心思', detail: '不是随手买的三样东西' },
  { mark: '时', label: '留下一个记忆', detail: '让这次见面本身成为礼物' }
]

const PROCESS = [
  { name: '看关系', detail: '读收礼人的已知偏好，读不到就如实说没有' },
  { name: '定主题', detail: '把场合翻译成一条心意，而不是堆功能' },
  { name: '挑构成', detail: '让每件东西承担一个角色，判据是「同时被用到」' },
  { name: '留余地', detail: '把风险和可替换项说清楚' }
]

const draft = ref({
  recipient: RECIPIENTS[0],
  occasion: OCCASIONS[0],
  budget: 800,
  signals: ['真的用得上', '看得出花了心思']
})

const toggleSignal = (label) => {
  const list = draft.value.signals
  const i = list.indexOf(label)
  if (i >= 0) list.splice(i, 1)
  else list.push(label)
}

const submitting = ref(false)
const submitError = ref('')
const runs = ref([])
const runningCount = computed(() => runs.value.filter((r) => r.status === 'running').length)

onMounted(async () => {
  runs.value = await giftApi.listRuns()
})

const begin = async () => {
  if (submitting.value) return
  submitting.value = true
  submitError.value = ''
  try {
    const run = await giftApi.createRun({
      recipient: draft.value.recipient,
      occasion: draft.value.occasion,
      budget: draft.value.budget,
      signals: draft.value.signals
    })
    router.push({ path: '/proxy', query: { run: run.id } })
  } catch (e) {
    submitError.value = e?.message || '创建失败，请重试'
  } finally {
    submitting.value = false
  }
}
</script>

<style lang="less" scoped>
/* 布局交给全局 .page。这里只保留送礼页特有的样式。
   印章走 PageHeader 的 #mark 插槽；这里只覆盖它的配色 ——
   送礼用暖金主色，与采购的 emerald 区分身份。 */
.page {
  --mark-bg: var(--gift-accent-soft);
  --mark-fg: var(--gift-accent);
}

/* 两栏：左表单 / 右说明。窄屏堆叠 */
.gf-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(260px, 0.6fr);
  gap: 32px;
  align-items: start;
}
@media (max-width: 900px) {
  .gf-grid { grid-template-columns: minmax(0, 1fr); gap: 24px; }
}

.gf-form {
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: var(--bg-surface);
  padding: 18px 20px 20px;
  max-width: 560px;
}
.gf-field { display: block; margin-bottom: 16px; }
.gf-label {
  display: block;
  margin-bottom: 7px;
  font-size: 0.76rem;
  color: var(--text-muted);
}
.gf-label-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 7px;
  .gf-label { margin-bottom: 0; }
  strong { font-size: 0.86rem; color: var(--text-strong); }
}
.gf-select {
  width: 100%;
  height: 34px;
  padding: 0 10px;
  font-family: var(--font-body);
  font-size: 0.82rem;
  color: var(--text);
  background: var(--bg-surface);
  border: 1px solid var(--border-strong);
  border-radius: var(--radius-sm);
  outline: none;
  &:focus { border-color: var(--gift-accent); }
}
.gf-range {
  width: 100%;
  accent-color: var(--gift-accent);
}
.gf-range-labels {
  display: flex;
  justify-content: space-between;
  margin-top: 4px;
  font-size: 0.68rem;
  color: var(--text-faint);
}

.gf-signals { display: flex; flex-direction: column; gap: 7px; }
.gf-signal {
  display: grid;
  grid-template-columns: 22px 1fr;
  grid-template-rows: auto auto;
  gap: 1px 9px;
  text-align: left;
  font-family: var(--font-body);
  padding: 9px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: transparent;
  cursor: pointer;
  transition: border-color 0.15s ease-out, background-color 0.15s ease-out;
  i {
    grid-row: span 2;
    align-self: center;
    width: 22px; height: 22px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 6px;
    background: var(--bg-sunken);
    color: var(--text-muted);
    font-style: normal;
    font-size: 0.72rem;
  }
  span { font-size: 0.8rem; color: var(--text-strong); }
  em {
    font-style: normal;
    font-size: 0.7rem;
    color: var(--text-faint);
    line-height: 1.4;
  }
  &:hover { border-color: var(--border-strong); }
  &.on {
    border-color: var(--gift-accent);
    background: var(--gift-accent-soft);
    i { background: var(--gift-accent); color: var(--on-accent); }
  }
}

.gf-submit {
  width: 100%;
  margin-top: 6px;
  padding: 11px;
  font-family: var(--font-body);
  font-size: 0.84rem;
  border: 1px solid var(--gift-accent);
  border-radius: var(--radius-sm);
  background: var(--gift-accent);
  color: var(--on-accent);
  cursor: pointer;
  transition: opacity 0.15s ease-out;
  &:hover:not(:disabled) { opacity: 0.88; }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}
.gf-err {
  margin: 8px 0 0;
  font-size: 0.76rem;
  color: var(--neg);
}

/* 右栏说明 */
.gf-steps {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 14px;
  li { display: flex; gap: 10px; }
}
.gf-step-no {
  flex: 0 0 auto;
  width: 20px; height: 20px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  border: 1px solid var(--border-strong);
  font-size: 0.68rem;
  color: var(--text-muted);
}
.gf-step-name {
  margin: 0;
  font-size: 0.82rem;
  font-weight: 600;
  color: var(--text-strong);
}
.gf-step-detail {
  margin: 2px 0 0;
  font-size: 0.74rem;
  line-height: 1.6;
  color: var(--text-muted);
}
.gf-note {
  margin: 18px 0 0;
  padding-top: 14px;
  border-top: 1px solid var(--border);
  font-size: 0.74rem;
  line-height: 1.7;
  color: var(--text-faint);
}
</style>
