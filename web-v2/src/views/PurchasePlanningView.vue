<template>
  <WizardShell
    title="采购规划"
    subtitle="一句话需求 → 分步走，当前步放大"
    icon="plan"
    status="采购规划 · 进行中"
    status-tone="live"
    :steps="steps"
    :req-title="card.title"
    :req-summary="reqSummary"
    :input-placeholder="appliedMsg ? '继续追问，例如：沙发放哪类目？' : '例如「总预算提到 8 万」→ 更新需求并重新交付'"
    :applied-msg="appliedMsg"
    @modify="applyModify"
  >
    <!-- 第 1 步：需求（结构化小信息卡） -->
    <template #step-need>
      <div class="req-card" @click="cardOpen = !cardOpen">
        <div class="rc-head">
          <span class="rc-badge">需求</span>
          <span class="rc-state">{{ card.state }}</span>
        </div>
        <div class="rc-title">{{ card.title }}</div>
        <div class="rc-fields">
          <div v-for="f in card.fields" :key="f.k" class="rcf">
            <span class="rcf-k">{{ f.k }}</span>
            <span class="rcf-v" :class="{ mono: f.mono }">{{ f.v }}</span>
          </div>
        </div>
        <div v-if="cardOpen" class="rc-more">
          <div v-for="f in card.more" :key="f.k" class="rcf">
            <span class="rcf-k">{{ f.k }}</span>
            <span class="rcf-v">{{ f.v }}</span>
          </div>
          <button class="rc-edit" type="button" @click.stop="drawer = 'add'">编辑需求</button>
        </div>
      </div>
      <button class="add-card" type="button" @click="drawer = 'add'">+ 新建需求卡片</button>
    </template>

    <!-- 第 2 步：拆解 -->
    <template #step-breakdown>
      <div v-for="g in groups" :key="g" class="grp">
        <div class="grp-label">
          {{ g }}
          <span class="mono grp-count">{{ groupItems(g).length }} 项 · {{ doneCount(g) }} 已下单</span>
        </div>
        <div
          v-for="it in groupItems(g)"
          :key="it.name"
          class="item"
          :class="{ done: it.done, blocked: it.blocked && !it.done }"
          @click="toggle(it)"
        >
          <span class="dot" :class="'st-' + statusOf(it)" />
          <span class="item-name" :class="{ dim: it.done }">{{ it.name }}</span>
          <span class="item-meta mono">{{ it.price ? '¥' + fmt(it.price) : '—' }} · {{ statusText(it) }}</span>
        </div>
      </div>
    </template>

    <!-- 第 3 步：比选 -->
    <template #step-compare>
      <div
        v-for="it in items"
        :key="it.name"
        class="item"
        :class="{ done: it.done, blocked: it.blocked && !it.done, open: openRow === it.name }"
        @click="toggle(it)"
      >
        <span class="dot" :class="'st-' + statusOf(it)" />
        <span class="item-name" :class="{ dim: it.done }">{{ it.name }}</span>
        <span class="item-meta mono">{{ it.price ? '¥' + fmt(it.price) : '—' }} · {{ statusText(it) }}</span>
        <p v-if="openRow === it.name" class="item-note">{{ it.note }}</p>
      </div>
    </template>

    <!-- 第 4 步：规划表 -->
    <template #step-plan>
      <div v-for="b in budgets" :key="b.name" class="bud">
        <div class="bud-head">
          <span>{{ b.name }}</span>
          <span class="mono">¥{{ fmt(b.total) }}</span>
        </div>
        <div class="bud-track" :style="{ width: share(b.total) }">
          <ThinBar :value="b.used" :max="b.total" :tone="b.used ? 'accent' : 'muted'" />
        </div>
        <div class="bud-used mono">{{ b.used ? '已花 ' + fmt(b.used) : '未开始' }}</div>
      </div>
      <div class="bud-sum">
        <span>剩余</span><span class="mono">¥{{ fmt(total - spent) }}</span>
      </div>

      <div class="sub-label">下单顺序</div>
      <div v-for="(o, i) in order" :key="o" class="prow-static">
        <span><span class="mono">{{ i + 1 }}</span> {{ o }}</span>
      </div>
      <p v-if="blockedText" class="warn-line">{{ blockedText }}</p>
    </template>

    <!-- 第 5 步：交付 -->
    <template #step-deliver>
      <p class="msg">{{ task.brief }}</p>
      <div class="files">
        <button
          v-for="f in task.files"
          :key="f.name"
          class="file"
          type="button"
          @click="openFileDrawer(f)"
        >
          <span class="file-icon" />
          <span class="file-name">{{ f.name }}</span>
          <span class="file-meta mono">{{ f.meta }}</span>
        </button>
      </div>
    </template>

    <template #panel>
      <div class="panel-head">
        <span>信息面板</span>
        <span class="panel-hint">跨步骤常看</span>
      </div>

      <div class="segs">
        <button
          v-for="s in segs"
          :key="s.key"
          class="seg"
          :class="{ on: seg === s.key }"
          type="button"
          @click="seg = s.key"
        >
          {{ s.label }}<span v-if="s.n" class="mono"> {{ s.n }}</span>
        </button>
      </div>

      <template v-if="seg === 'budget'">
        <div v-for="b in budgets" :key="b.name" class="bud">
          <div class="bud-head">
            <span>{{ b.name }}</span>
            <span class="mono">{{ fmt(b.total) }}</span>
          </div>
          <div class="bud-track" :style="{ width: share(b.total) }">
            <ThinBar :value="b.used" :max="b.total" :tone="b.used ? 'accent' : 'muted'" />
          </div>
          <div class="bud-used mono">{{ b.used ? '已花 ' + fmt(b.used) : '未开始' }}</div>
        </div>
        <div class="bud-sum">
          <span>剩余</span><span class="mono">¥{{ fmt(total - spent) }}</span>
        </div>
      </template>

      <template v-else>
        <div class="sub-label">依赖与提醒</div>
        <p v-for="n in notes" :key="n" class="why">· {{ n }}</p>
        <p v-if="blockedText" class="warn-line">{{ blockedText }}</p>
      </template>
    </template>

    <template #overlays>
      <Drawer :open="drawer === 'file'" :title="activeFile ? activeFile.name : ''" @close="drawer = ''">
        <template v-if="activeFile && activeFile.kind === 'doc'">
          <div v-for="b in budgets" :key="b.name" class="dw-bud">
            <div class="dw-bud-head">
              <span>{{ b.name }}</span>
              <span class="mono">¥{{ fmt(b.total) }}</span>
            </div>
            <div class="bud-track" :style="{ width: share(b.total) }">
              <ThinBar :value="b.used" :max="b.total" :tone="b.used ? 'accent' : 'muted'" />
            </div>
          </div>
          <p class="dw-note">总预算 ¥{{ fmt(total) }} · 已花 ¥{{ fmt(spent) }} · 剩余 ¥{{ fmt(total - spent) }}</p>
        </template>
        <template v-else>
          <div v-for="it in items" :key="it.name" class="dw-item">
            <div class="dw-item-head">
              <span class="dw-item-name">{{ it.name }}</span>
              <span class="mono">{{ it.price ? '¥' + fmt(it.price) : '—' }}</span>
            </div>
            <p class="dw-item-why">{{ it.note }}</p>
          </div>
        </template>
      </Drawer>

      <Drawer :open="drawer === 'add'" title="新建需求卡片" @close="drawer = ''">
        <div class="form">
          <label v-for="f in addFields" :key="f.k" class="form-row">
            <span class="form-k">{{ f.k }}<em v-if="f.req">*</em></span>
            <input v-model="f.v" class="form-input" :placeholder="f.ph" />
          </label>
        </div>
        <button class="form-submit" type="button" @click="drawer = ''; appliedMsg = '新卡片已提交，正在执行…（演示）'">
          提交卡片
        </button>
      </Drawer>
    </template>
  </WizardShell>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'
import ThinBar from '@/components/common/ThinBar.vue'
import Drawer from '@/components/common/Drawer.vue'
import WizardShell from '@/components/common/WizardShell.vue'

const total = 60000
const cardOpen = ref(false)
const seg = ref('budget')
const openRow = ref('')
const drawer = ref('')
const activeFile = ref(null)
const appliedMsg = ref('')

const card = reactive({
  title: '采购需求 · 装修',
  state: '已提交',
  fields: [
    { k: '场景', v: '装修' },
    { k: '总预算', v: '¥60,000', mono: true },
    { k: '里程碑', v: '硬装完工 10/15', mono: true },
    { k: '工期', v: '约 6 周', mono: true }
  ],
  more: [
    { k: '空间约束', v: '阳台需预留水电点位' },
    { k: '备注', v: '有老人同住，优先静音' }
  ]
})
const reqSummary = computed(() => card.fields.map((f) => f.v).join(' · '))

// sub 是那一步的「结论摘要」，让整条轨迹一眼可读，而不只是把已完成的步骤变灰
const steps = [
  { key: 'need', label: '需求', sub: '已提交', desc: '确认场景、预算与里程碑' },
  { key: 'breakdown', label: '拆解', sub: '3 类', desc: '按品类拆成采购分组' },
  { key: 'compare', label: '比选', sub: '7 项', desc: '逐项比选并标注状态' },
  { key: 'plan', label: '规划表', sub: '6 万', desc: '预算分配与下单顺序' },
  { key: 'deliver', label: '交付', desc: '完整采购清单与文档' }
]

const task = reactive({
  status: 'done',
  meta: '4 个工具 · 12.4s',
  steps: [
    { name: '派发 · 采购规划师', state: 'done', time: '' },
    { name: 'search_products', state: 'done', time: '1.4s' },
    { name: 'query_category_knowledge', state: 'done', time: '0.7s' },
    { name: 'get_products_specs_batch', state: 'done', time: '2.1s' }
  ],
  brief: '按 6 万总预算拆成 4 类，先定硬装前置项；冰箱等完工后再下单。',
  files: [
    { name: '采购清单', meta: '7 项', kind: 'card' },
    { name: '预算分配表', meta: '4 类目', kind: 'doc' }
  ]
})

const openFileDrawer = (f) => {
  activeFile.value = f
  drawer.value = 'file'
}

const applyModify = (text) => {
  const t = String(text || '').trim()
  if (!t) return
  const m = t.match(/(\d[\d,]*)/)
  if (m && /预算|万/.test(t)) {
    let n = Number(m[1].replace(/,/g, ''))
    if (/万/.test(t)) n = n * 10000
    const field = card.fields.find((f) => f.k === '总预算')
    if (field) field.v = '¥' + n.toLocaleString('en-US')
    appliedMsg.value = `已把「总预算」更新为 ¥${n.toLocaleString('en-US')}，并重新交付`
  } else {
    appliedMsg.value = '已收到这条要求，正在重新执行…（演示）'
  }
}

const addFields = reactive([
  { k: '场景', v: '', ph: '装修 / 换季 / 搬家 / 开学', req: true },
  { k: '总预算', v: '', ph: '¥60,000', req: true },
  { k: '里程碑', v: '', ph: '如「硬装完工 10/15」' },
  { k: '空间约束', v: '', ph: '可选，如「阳台预留水电」' }
])

// 面板只放「跨步骤常看」的信息：预算占用 + 受阻项。
// 清单明细已在「拆解 / 比选」步、下单顺序已在「规划表」步，不在面板里重复第二遍。
const segs = computed(() => [
  { key: 'budget', label: '预算', n: budgets.length },
  { key: 'dep', label: '依赖', n: blockedItems.value.length }
])

const groups = ['硬装前置', '家电', '软装']

const items = ref([
  { name: '确认厨卫尺寸', group: '硬装前置', price: 0, done: true, note: '硬装前置项，已确认' },
  { name: '阳台水电点位', group: '硬装前置', price: 0, done: true, note: '硬装前置项，已确认' },
  { name: '洗烘一体机', group: '家电', price: 5499, done: true, note: '预算 6000，安装尺寸已复核' },
  { name: '扫地机器人', group: '家电', price: 2799, done: true, note: '家里有地毯，注意地毯识别' },
  { name: '对开门冰箱', group: '家电', price: 5699, done: false, blocked: true, dep: '硬装完工', note: '等硬装完工再下单，避免灰尘' },
  { name: '遮光窗帘', group: '软装', price: 1200, done: false, note: '需先量窗宽再定' },
  { name: '客厅地毯', group: '软装', price: 1800, done: false, note: '待地面完工后选购' }
])

const budgets = [
  { name: '家电', total: 25000, used: 8298 },
  { name: '家具', total: 20000, used: 0 },
  { name: '软装', total: 10000, used: 0 },
  { name: '灯具', total: 5000, used: 0 }
]

const order = ['硬装前置', '家电（大件）', '软装 · 灯具']
const notes = ['冰箱等完工再下单，避免灰尘', '窗帘需先量窗宽']

const spent = computed(() => items.value.filter((i) => i.done).reduce((s, i) => s + i.price, 0))

// 受阻项统一由 items 派生 —— 原先「1 项受阻：冰箱依赖硬装完工」是两处硬编码字符串，
// 改了 items 不会同步，属于文案与数据不同源。
const blockedItems = computed(() => items.value.filter((i) => i.blocked && !i.done))
const blockedText = computed(() => {
  const b = blockedItems.value
  if (!b.length) return ''
  return `${b.length} 项受阻：${b.map((i) => `${i.name}依赖「${i.dep || '前置项'}」`).join('；')}`
})
const maxBudget = Math.max(...budgets.map((b) => b.total))
const share = (t) => Math.round((t / maxBudget) * 100) + '%'

const groupItems = (g) => items.value.filter((i) => i.group === g)
const doneCount = (g) => groupItems(g).filter((i) => i.done).length
const statusOf = (it) => (it.blocked && !it.done ? 'blocked' : it.done ? 'done' : 'pending')
const statusText = (it) => ({ blocked: '等完工', done: '已下单', pending: '待定' }[statusOf(it)])
const toggle = (it) => {
  if (it.blocked && !it.done) return
  it.done = !it.done
  openRow.value = openRow.value === it.name ? '' : it.name
}
const fmt = (n) => n.toLocaleString('en-US')
</script>

<style lang="less" scoped>
.mono { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }

/* 需求卡 */
.req-card {
  padding: 14px 18px;
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: var(--bg-surface);
  cursor: pointer;
  transition: border-color 0.15s ease-out;

  &:hover { border-color: var(--accent-500); }
}
.rc-badge {
  font-size: 0.72rem;
  letter-spacing: 0.05em;
  color: var(--on-accent);
  background: var(--accent-solid);
  padding: 2px 9px;
  border-radius: 6px;
}
.rc-title { font-size: 0.96rem; font-weight: 600; color: var(--text-strong); margin: 9px 0 11px; }
.rc-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 0;

  .rc-state { font-size: 0.72rem; color: var(--pos); }
}
.rc-fields {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 22px;
}
.rcf {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  font-size: 0.82rem;

  .rcf-k { color: var(--text-muted); font-size: 0.73rem; }
  .rcf-v { color: var(--text); }
}
.rc-more {
  margin-top: 12px;
  padding-top: 11px;
  border-top: 1px solid var(--border);

  .rcf { margin-bottom: 7px; }
  .rc-edit {
    margin-top: 8px;
    padding: 5px 12px;
    font-size: 0.74rem;
    color: var(--text);
    background: transparent;
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    cursor: pointer;

    &:hover { border-color: var(--border-strong); }
  }
}
.add-card {
  margin: 14px 0 6px;
  width: 100%;
  padding: 9px 15px;
  font-size: 0.78rem;
  color: var(--text-muted);
  background: transparent;
  border: 1px dashed var(--border-strong);
  border-radius: var(--radius-sm);
  cursor: pointer;

  &:hover { color: var(--text); border-color: var(--accent-500); }
}

.msg {
  margin: 0 0 14px;
  font-size: 0.9rem;
  line-height: 1.8;
  color: var(--text);
}

/* 拆解 / 比选：清单 */
.grp { margin-bottom: 14px; }
.grp-label {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  font-size: 0.74rem;
  font-weight: 600;
  letter-spacing: 0.03em;
  color: var(--text-strong);
  margin-bottom: 7px;

  .grp-count { font-size: 0.72rem; font-weight: 400; color: var(--text-muted); }
}
.item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  margin-bottom: 7px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: border-color 0.15s ease-out;

  &:hover { border-color: var(--border-strong); }
  &.done { opacity: 0.78; }
  &.blocked { opacity: 0.7; cursor: not-allowed; }
  &.open { border-color: var(--accent-500); }

  .dot {
    flex: 0 0 7px;
    width: 7px;
    height: 7px;
    border-radius: 50%;
    background: var(--text-muted);

    &.st-done { background: var(--pos); }
    &.st-blocked { background: var(--warn); }
    &.st-pending { background: var(--text-muted); }
  }
  .item-name { flex: 1 1 auto; font-size: 0.84rem; color: var(--text-strong); }
  .item-name.dim { color: var(--text-muted); }
  .item-meta { font-size: 0.74rem; color: var(--text-muted); white-space: nowrap; }
}
.item-note {
  flex-basis: 100%;
  margin: 2px 0 0 17px;
  font-size: 0.72rem;
  line-height: 1.6;
  color: var(--text-muted);
}

/* 规划表 */
.bud { margin-bottom: 14px; }
.bud-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 5px;
  font-size: 0.82rem;

  .mono { font-size: 0.76rem; color: var(--text-muted); }
}
.bud-track { max-width: 100%; }
.bud-used { margin-top: 4px; font-size: 0.72rem; color: var(--text-muted); }
.bud-sum {
  display: flex;
  justify-content: space-between;
  margin-top: 14px;
  padding-top: 11px;
  border-top: 1px solid var(--border);
  font-size: 0.82rem;
  color: var(--text-strong);
}

.sub-label { font-size: 0.72rem; letter-spacing: 0.05em; color: var(--text-muted); margin: 14px 0 6px; }
.prow-static {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 2px;
  font-size: 0.8rem;
  color: var(--text);
  border-bottom: 1px solid var(--border);

  &:last-of-type { border-bottom: none; }
  .mono { color: var(--text-muted); font-size: 0.72rem; margin-right: 6px; }
}
.warn-line { margin: 10px 0 0; font-size: 0.74rem; color: var(--warn); }

/* 交付文件 */
.files { display: flex; flex-wrap: wrap; gap: 9px; margin-top: 4px; }
.file {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 8px 13px;
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: border-color 0.15s ease-out;

  &:hover { border-color: var(--accent-500); }

  .file-icon {
    width: 14px;
    height: 18px;
    border: 1px solid var(--border-strong);
    border-radius: 2px;
  }
  .file-name { font-size: 0.8rem; color: var(--text-strong); }
  .file-meta { font-size: 0.72rem; color: var(--text-muted); }
}

/* 信息面板 */
.panel-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 12px;
  font-size: 0.72rem;
  letter-spacing: 0.06em;
  color: var(--text-muted);

  .panel-hint { font-size: 0.72rem; }
}
.segs { display: flex; gap: 4px; margin-bottom: 12px; }
.seg {
  padding: 4px 10px;
  font-size: 0.74rem;
  color: var(--text-muted);
  background: transparent;
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;

  &.on { background: var(--bg-sunken); color: var(--text-strong); }
}

.why {
  margin: 0 0 4px;
  font-size: 0.72rem;
  line-height: 1.6;
  color: var(--text-muted);
}

/* 抽屉内容 */
.dw-bud { margin-bottom: 14px; }
.dw-bud-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  margin-bottom: 5px;
  font-size: 0.78rem;

  .mono { font-size: 0.74rem; color: var(--text-muted); }
}
.dw-item {
  padding: 11px 0;
  border-bottom: 1px solid var(--border);

  &:last-child { border-bottom: none; }
  .dw-item-head {
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    gap: 12px;

    .dw-item-name { font-size: 0.84rem; font-weight: 600; color: var(--text-strong); }
    .mono { font-size: 0.8rem; color: var(--text-strong); }
  }
  .dw-item-why { margin: 6px 0 0; font-size: 0.74rem; line-height: 1.6; color: var(--text-muted); }
}
.dw-note { margin: 12px 0 0; font-size: 0.72rem; color: var(--text-muted); }

.form { display: flex; flex-direction: column; gap: 12px; }
.form-row {
  display: flex;
  align-items: center;
  gap: 12px;

  .form-k {
    flex: 0 0 76px;
    font-size: 0.76rem;
    color: var(--text-muted);

    em { font-style: normal; color: var(--neg); margin-left: 2px; }
  }
  .form-input {
    flex: 1 1 auto;
    min-width: 0;
    padding: 8px 11px;
    font-family: var(--font-body);
    font-size: 0.8rem;
    color: var(--text);
    background: var(--bg-base);
    border: 1px solid var(--border);
    border-radius: var(--radius-sm);
    outline: none;

    &::placeholder { color: var(--text-muted); }
    &:focus { border-color: var(--accent-500); }
  }
}
.form-submit {
  width: 100%;
  margin-top: 18px;
  padding: 9px 14px;
  font-size: 0.8rem;
  color: var(--on-accent);
  background: var(--accent-solid);
  border: none;
  border-radius: var(--radius-sm);
  cursor: pointer;

  &:hover { background: var(--accent-600); }
}
</style>
