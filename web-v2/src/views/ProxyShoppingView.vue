<template>
  <WizardShell
    title="代购送礼"
    subtitle="一句话需求 → 分步走，当前步放大"
    icon="gift"
    status="礼物方案 · 进行中"
    status-tone="live"
    :steps="steps"
    :req-title="card.title"
    :req-summary="reqSummary"
    :input-placeholder="appliedMsg ? '继续追问，例如：和颈部按摩仪比哪个更值？' : '例如「预算放宽到 1500」→ 更新需求并重新交付'"
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

    <!-- 第 2 步：分析 -->
    <template #step-analyze>
      <p class="msg">根据妈妈的档案（怕吵、卧室偏干、不爱花哨），我先检索了商品库，并拉取详情与品类知识做对比…</p>
      <ExecStatus :status="task.status" :meta="task.meta" :steps="task.steps" />
      <p class="msg">{{ task.brief }}</p>
    </template>

    <!-- 第 3 步：候选 -->
    <template #step-candidate>
      <div class="deliver">
        <div
          v-for="g in gifts"
          :key="g.name"
          class="cand"
          :class="{ open: openGift === g.name }"
          @click="openGift = openGift === g.name ? '' : g.name"
        >
          <div class="cand-head">
            <span class="cand-name">{{ g.name }}</span>
            <span class="cand-meta mono">¥{{ g.price }} · 契合 {{ g.fit }}</span>
          </div>
          <div v-if="openGift === g.name" class="cand-body">
            <div v-for="d in g.dims" :key="d.k" class="dim">
              <span class="dim-k">{{ d.k }}</span>
              <ThinBar :value="d.v" :max="100" :tone="d.v >= 70 ? 'accent' : 'warn'" />
              <span class="dim-v mono">{{ d.v }}</span>
            </div>
            <p class="why">依据：{{ g.why }}</p>
          </div>
        </div>

        <button class="drawer-link" type="button" @click="drawer = 'compare'">查看完整对比 ▸</button>

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
      </div>
    </template>

    <!-- 第 4 步：交付 -->
    <template #step-deliver>
      <div class="pick">
        <span class="pick-tag">首选</span>
        <div class="pick-name">{{ topPick.name }}<span class="mono pick-fit">契合 {{ topPick.fit }}</span></div>
        <p class="pick-why">{{ topPick.why }}</p>
      </div>
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

      <template v-if="seg === 'file'">
        <div class="person">妈妈 · 58 岁</div>
        <p class="person-meta">给 TA 买过 2 次 · 上次评价「实用，不占地」</p>
        <div v-for="t in traits" :key="t.text" class="trait">
          <span class="trait-src" :class="'src-' + t.src">{{ t.src === 'known' ? '已知' : '推断' }}</span>
          <span>{{ t.text }}</span>
        </div>
        <div class="panel-sep" />
        <div class="sub-label">给 TA 送过</div>
        <div v-for="h in history" :key="h.n" class="prow-static">
          <span>{{ h.n }}</span><span class="mono">{{ h.d }}</span>
        </div>
      </template>

      <template v-else>
        <p v-if="!picked.length" class="empty-hint">还没有加入备选的礼物 —— 在「候选」步里挑一个，用底部对话说「加入备选」</p>
        <div v-else>
          <div v-for="p in picked" :key="p.name" class="prow-static">
            <span>{{ p.name }}</span><span class="mono">¥{{ p.price }}</span>
          </div>
        </div>
      </template>
    </template>

    <template #overlays>
      <Drawer :open="drawer === 'file'" :title="activeFile ? activeFile.name : ''" @close="drawer = ''">
        <template v-if="activeFile && activeFile.kind === 'doc'">
          <div class="cmp">
            <div class="cmp-row cmp-head">
              <span>维度</span>
              <span v-for="g in gifts" :key="g.name">{{ g.name }}</span>
            </div>
            <div v-for="d in dimKeys" :key="d" class="cmp-row">
              <span class="cmp-k">{{ d }}</span>
              <span v-for="g in gifts" :key="g.name" class="mono">{{ dimOf(g, d) }}</span>
            </div>
          </div>
        </template>
        <template v-else>
          <div v-for="g in gifts" :key="g.name" class="dw-item">
            <div class="dw-item-head">
              <span class="dw-item-name">{{ g.name }}</span>
              <span class="mono">¥{{ g.price }}</span>
            </div>
            <p class="dw-item-why">{{ g.why }}</p>
          </div>
        </template>
      </Drawer>

      <Drawer :open="drawer === 'compare'" title="完整对比" :width="520" @close="drawer = ''">
        <div class="cmp">
          <div class="cmp-row cmp-head">
            <span>维度</span>
            <span v-for="g in gifts" :key="g.name">{{ g.name }}</span>
          </div>
          <div v-for="d in dimKeys" :key="d" class="cmp-row">
            <span class="cmp-k">{{ d }}</span>
            <span v-for="g in gifts" :key="g.name" class="mono">{{ dimOf(g, d) }}</span>
          </div>
        </div>
        <p class="dw-note">分数越高越好；来源：商品数据 + 品类知识（演示）</p>
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
import ExecStatus from '@/components/common/ExecStatus.vue'
import Drawer from '@/components/common/Drawer.vue'
import WizardShell from '@/components/common/WizardShell.vue'

const cardOpen = ref(false)
const openGift = ref('')
const seg = ref('file')
const drawer = ref('')
const activeFile = ref(null)
const appliedMsg = ref('')

const card = reactive({
  title: '送礼需求 · 妈妈生日',
  state: '已提交',
  fields: [
    { k: '收礼人', v: '妈妈' },
    { k: '场合', v: '生日' },
    { k: '预算', v: '¥1,000 内', mono: true },
    { k: '送达', v: '10/01 前', mono: true }
  ],
  more: [
    { k: '忌讳', v: '无' },
    { k: '备注', v: '偏实用，不要闲置' }
  ]
})
const reqSummary = computed(() => card.fields.map((f) => f.v).join(' · '))

// sub 是那一步的「结论摘要」，让整条轨迹一眼可读
const steps = [
  { key: 'need', label: '需求', sub: '已提交', desc: '确认送礼对象与约束' },
  { key: 'analyze', label: '分析', sub: '4 工具', desc: '智能体检索商品、比对品类知识' },
  { key: 'candidate', label: '候选', sub: '3 个', desc: '按契合度排序的候选礼物' },
  { key: 'deliver', label: '交付', desc: '最终建议与对比文档' }
]

const task = reactive({
  status: 'done',
  meta: '4 个工具 · 8.2s',
  steps: [
    { name: '派发 · 送礼顾问', state: 'done', time: '' },
    { name: 'search_products', state: 'done', time: '1.2s' },
    { name: 'get_product_full_detail', state: 'done', time: '0.8s' },
    { name: 'query_category_knowledge', state: 'done', time: '0.6s' }
  ],
  brief: '按「怕吵 + 卧室偏干」，静音加湿器最合适；另有两个方向可备选。',
  files: [
    { name: '候选卡片', meta: '3 个', kind: 'card' },
    { name: '对比文档', meta: '3 款横比', kind: 'doc' }
  ]
})

const gifts = [
  {
    name: '静音加湿器 4L', price: '329', fit: 88,
    why: '档案「怕吵 + 卧室偏干」两条都命中，且不占地方',
    dims: [
      { k: '体面度', v: 72 }, { k: '不易闲置', v: 92 },
      { k: '包装', v: 60 }, { k: '好退换', v: 90 }, { k: '送达时效', v: 95 }
    ]
  },
  {
    name: '保温杯礼盒', price: '329', fit: 79,
    why: '自带礼盒，符合「不爱花哨」；但偏日常',
    dims: [
      { k: '体面度', v: 78 }, { k: '不易闲置', v: 88 },
      { k: '包装', v: 92 }, { k: '好退换', v: 85 }, { k: '送达时效', v: 92 }
    ]
  },
  {
    name: '颈部按摩仪', price: '599', fit: 64,
    why: '实用但对「怕吵」无帮助，且包装偏简陋',
    dims: [
      { k: '体面度', v: 70 }, { k: '不易闲置', v: 55 },
      { k: '包装', v: 45 }, { k: '好退换', v: 85 }, { k: '送达时效', v: 90 }
    ]
  }
]
const topPick = gifts[0]

const openFileDrawer = (f) => {
  activeFile.value = f
  drawer.value = 'file'
}

const applyModify = (text) => {
  const t = String(text || '').trim()
  if (!t) return
  const m = t.match(/(\d[\d,]*)/)
  if (m && /预算/.test(t)) {
    const n = Number(m[1].replace(/,/g, ''))
    const field = card.fields.find((f) => f.k === '预算')
    if (field) field.v = '¥' + n.toLocaleString('en-US') + ' 内'
    appliedMsg.value = `已把「预算」更新为 ¥${n.toLocaleString('en-US')}，并重新交付`
  } else {
    appliedMsg.value = '已收到这条要求，正在重新执行…（演示）'
  }
}

// 面板只放「跨步骤常看」的信息：收礼人档案 + 备选。
// 候选明细已在「候选」步里，不在面板里重复第二遍。
const segs = computed(() => [
  { key: 'file', label: '档案', n: history.length },
  { key: 'pick', label: '备选', n: picked.length }
])

const dimKeys = ['体面度', '不易闲置', '包装', '好退换', '送达时效']
const dimOf = (g, k) => (g.dims.find((d) => d.k === k) || {}).v ?? '—'

const addFields = reactive([
  { k: '收礼人', v: '', ph: '妈妈 / 同事…', req: true },
  { k: '场合', v: '', ph: '生日 / 节日 / 探访', req: true },
  { k: '预算', v: '', ph: '¥1,000 内', req: true },
  { k: '送达时间', v: '', ph: '10/01 前' },
  { k: '忌讳', v: '', ph: '可选，如「不吃甜」' }
])

const traits = [
  { src: 'known', text: '偏实用 · 不爱花哨' },
  { src: 'infer', text: '卧室偏干 · 怕吵' }
]

const history = [
  { n: '加湿器 · 评价「实用」', d: '2025/12' },
  { n: '保暖内衣 · 已闲置', d: '2025/01' }
]

const picked = []
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

/* 交付物 */
.deliver { margin-top: 2px; }
.cand {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: var(--bg-surface);
  margin-bottom: 10px;
  cursor: pointer;
  transition: border-color 0.15s ease-out;

  &:hover { border-color: var(--border-strong); }
  &.open { border-color: var(--accent-500); }
}
.cand-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;

  .cand-name { font-size: 0.92rem; font-weight: 600; color: var(--text-strong); }
  .cand-meta { font-size: 0.76rem; color: var(--text-muted); }
}
.cand-body { padding: 2px 16px 13px; border-top: 1px solid var(--border); }
.dim {
  display: grid;
  grid-template-columns: 58px minmax(0, 1fr) 24px;
  align-items: center;
  gap: 9px;
  padding: 3px 0;

  .dim-k { font-size: 0.72rem; color: var(--text-muted); }
  .dim-v { font-size: 0.72rem; color: var(--text-muted); text-align: right; }
}
.why {
  margin: 9px 0 0;
  font-size: 0.74rem;
  line-height: 1.6;
  color: var(--text-muted);
}

/* 交付首选 */
.pick {
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: var(--bg-surface);
  padding: 13px 16px;
  margin-bottom: 14px;

  .pick-tag {
    font-size: 0.72rem; letter-spacing: 0.05em;
    color: var(--on-accent); background: var(--accent-solid);
    padding: 2px 8px; border-radius: 5px;
  }
  .pick-name {
    display: flex; align-items: baseline; gap: 10px;
    margin: 9px 0 4px;
    font-size: 1rem; font-weight: 600; color: var(--text-strong);
    .pick-fit { font-size: 0.76rem; color: var(--accent-600); }
  }
  .pick-why { margin: 0; font-size: 0.76rem; line-height: 1.6; color: var(--text-muted); }
}

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

.prow-static {
  display: flex;
  justify-content: space-between;
  gap: 10px;
  padding: 7px 2px;
  font-size: 0.78rem;
  color: var(--text);
  border-bottom: 1px solid var(--border);

  &:last-child { border-bottom: none; }
  .mono { color: var(--text-muted); font-size: 0.72rem; }
}

.person { font-size: 0.84rem; font-weight: 600; color: var(--text-strong); }
.person-meta { margin: 5px 0 12px; font-size: 0.74rem; line-height: 1.6; color: var(--text-muted); }
.trait {
  display: flex;
  gap: 9px;
  padding: 5px 0;
  font-size: 0.76rem;

  .trait-src { flex: 0 0 28px; font-size: 0.72rem; }
  .src-known { color: var(--pos); }
  .src-infer { color: var(--text-muted); }
}
.panel-sep { height: 1px; background: var(--border); margin: 12px 0; }
.sub-label { font-size: 0.72rem; letter-spacing: 0.05em; color: var(--text-muted); margin-bottom: 6px; }

.drawer-link {
  margin-top: 12px;
  padding: 0;
  font-size: 0.76rem;
  color: var(--accent-600);
  background: transparent;
  border: none;
  cursor: pointer;
}
.empty-hint { margin: 0; font-size: 0.72rem; line-height: 1.6; color: var(--text-muted); }

/* 抽屉内容 */
.cmp {
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.cmp-row {
  display: grid;
  grid-template-columns: 72px repeat(3, minmax(0, 1fr));
  gap: 8px;
  padding: 8px 11px;
  font-size: 0.74rem;
  color: var(--text);
  border-bottom: 1px solid var(--border);

  &:last-child { border-bottom: none; }
  span:not(:first-child) { text-align: right; }
  .cmp-k { color: var(--text-muted); }
  .mono { color: var(--text-strong); }
}
.cmp-head {
  background: var(--bg-sunken);
  font-size: 0.72rem;
  color: var(--text-muted);
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
