<template>
  <div class="page">
    <PageHeader
      title="采购规划"
      desc="把组合采购拆成清单、排出顺序，取舍过程留在决策图上可回看"
    >
      <template #mark>采</template>
      <template #stats>
        <span class="stat-pill">进行中 <b>{{ runningCount }}</b> 个</span>
        <span v-if="awaitingCount" class="stat-pill">待你确认 <b>{{ awaitingCount }}</b> 个</span>
      </template>
      <template #actions>
        <a-button size="small" class="lucide-icon-btn" @click="router.push('/tasks')">
          <ClipboardList :size="14" /><span>监控任务</span>
        </a-button>
      </template>
    </PageHeader>

    <!-- 输入形式入口：结构化表单，让用户把需求填实而不是组织语言 -->
    <section class="page-section">
      <div class="page-section-head">
        <h2 class="page-section-title">描述你的采购</h2>
        <span class="page-section-desc">选好场景与预算即可开始</span>
      </div>

      <div class="pe-form">
        <div v-for="f in ENTRY_FORM" :key="f.key" class="pe-field">
          <p class="pe-label">
            {{ f.label }}<em v-if="f.required">*</em>
          </p>
          <div class="pe-chips">
            <button
              v-for="opt in f.options"
              :key="opt"
              class="pe-chip"
              :class="{ on: isPicked(f, opt) }"
              type="button"
              @click="pick(f, opt)"
            >
              {{ f.key === 'when' && opt === '指定日期' ? '▦ ' + opt : opt }}
            </button>
          </div>
        </div>

        <button class="pe-submit" type="button" :disabled="submitting" @click="startFromForm">
          {{ submitting ? '正在创建任务…' : '生成采购方案 ›' }}
        </button>
        <p v-if="submitError" class="pe-err">{{ submitError }}</p>
      </div>
    </section>

    <!-- 预设方案：点一张 = 自动填好场景/预算/周期，直接带参数进工作台 -->
    <section class="page-section">
      <div class="page-section-head">
        <h2 class="page-section-title">或从预设方案开始</h2>
        <span class="page-section-meta">点击直接进入工作台</span>
      </div>
      <div class="tile-grid">
        <button
          v-for="p in PRESET_PLANS"
          :key="p.id"
          class="tile pe-card"
          type="button"
          @click="startFromPreset(p)"
        >
          <span class="pe-card-title">{{ p.title }}</span>
          <span class="pe-card-meta mono">{{ p.budget }} · {{ p.duration }}</span>
          <span class="pe-card-desc">{{ p.desc }}</span>
        </button>
      </div>
    </section>

    <!--
      ═══════════════════════════════════════════════════════════════
      采购历史
      ═══════════════════════════════════════════════════════════════
      用户原话：「在入口加个类似聊天记录的采购历史对话，点击生成交付即可
      在历史记录将待交付转变成已交付」。

      它同时解决两件事：
        · 入口页原先只有「开始新的」——推演完的记录没有回来的路（除非
          记得从档案页绕）。这里列全，点一条直接回那个工作台。
        · 「生成交付」的**结果**要看得见。交付前这里标「待交付」，交付后
          变成「已交付 + 时刻」——历史列表就是那个变化的落点。

      排序：进行中的在最上（用户最可能回去看），其余按时间倒序。
    -->
    <section v-if="history.length" class="page-section">
      <div class="page-section-head">
        <h2 class="page-section-title">采购历史</h2>
        <span class="page-section-meta">共 {{ runs.length }} 条</span>
      </div>

      <div class="ph-list">
        <button
          v-for="r in history"
          :key="r.id"
          class="ph-row"
          type="button"
          @click="openRun(r)"
        >
          <!-- 左侧：交付/推演状态。一眼分清「哪些还在跑、哪些已经拿走了」 -->
          <span class="ph-state" :class="`is-${stateOf(r)}`">
            {{ STATE_LABEL[stateOf(r)] }}
          </span>

          <span class="ph-main">
            <span class="ph-title">{{ r.scene || '未命名采购' }}<template
              v-if="r.budget"> · {{ r.budget }}</template></span>
            <span class="ph-sub">{{ r.subject || '—' }}</span>
          </span>

          <span class="ph-num mono">
            <template v-if="r.summary?.categories">{{ r.summary.categories }} 个品类</template>
            <template v-if="r.summary?.total != null"> · ¥{{ fmtMoney(r.summary.total) }}</template>
          </span>
          <span class="ph-when mono">{{ whenText(r) }}</span>
        </button>
      </div>
    </section>
  </div>
</template>

<script setup>
/**
 * 采购智能体 · 对话入口页
 *
 * 入口页的职责是「收敛意图」，把模糊需求变成结构化参数，然后交给工作台执行。
 * 所以这里只有三块：身份区、结构化表单、预设方案。
 *
 * 2026-09-24 对齐改造：原先自绘 .pe/.pe-inner + max-width:680px 居中，
 * 内容左边界落在 x=405，而全站标准页（.page）是 x=82。改用项目既定的
 * .page + PageHeader（page.less 开头写明它就是「替代各页漂移的
 * max-width/padding」），与 /agents、/mcps、/tasks 一致。
 */
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ClipboardList } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import { planningApi } from '@/apis/planning_api'
// 入口配置（预设方案 / 表单选项）从 data/purchaseDemo.js 拆到 data/planningEntryConfig.js
import { ENTRY_FORM, PRESET_PLANS } from '@/data/planningEntryConfig'

const router = useRouter()

const picked = ref({
  scene: '装修',
  budget: '¥6万',
  when: '下月开工',
  constraints: ['有老人', '要静音']
})

// 进行中的任务数：来自 GET /api/planning/runs。
// 接口不可用时如实为 0（planningApi 内部会置 demoStatus.planning）。
const runs = ref([])
const runningCount = computed(() => runs.value.filter((r) => r.status === 'running').length)
const awaitingCount = computed(() => runs.value.filter((r) => r.status === 'awaiting').length)

/**
 * 一条记录的状态 —— 四态。
 *
 * ⚠️ 「已交付」与「已收敛」是**两件事**，别合成一个：
 *   converged  方案算好了，但用户还没拿走
 *   delivered  用户点了「生成交付」，确认拿走
 * 用户要的正是这个区分（「将待交付转变成已交付」）。合成一个的话，
 * 历史列表里就分不清「哪些我还没处理」。
 */
const stateOf = (r) => {
  if (r.delivered) return 'delivered'
  if (r.status === 'converged') return 'pending'
  if (r.status === 'failed') return 'failed'
  return 'running'
}

const STATE_LABEL = {
  delivered: '已交付',
  pending: '待交付',
  running: '推演中',
  failed: '失败',
}

/**
 * 历史排序：**等待用户动作的排最前**，其余按时间倒序。
 *
 * 理由：这一栏的用处是「回到某次采购」。用户最可能回去的是「刚交付完
 * 想去看看」和「还在跑、想盯进度」的，而不是上周那条已经归档的。
 */
const history = computed(() => {
  const rank = { pending: 0, running: 1, delivered: 2, failed: 3 }
  return [...runs.value].sort((a, b) => {
    const d = (rank[stateOf(a)] ?? 9) - (rank[stateOf(b)] ?? 9)
    if (d !== 0) return d
    return new Date(b.created_at || 0) - new Date(a.created_at || 0)
  })
})

const fmtMoney = (v) => {
  const n = Number(v)
  if (!Number.isFinite(n)) return '—'
  return Number.isInteger(n) ? n.toLocaleString('en-US') : n.toFixed(2)
}

/** 相对时间：今天只给时:分，一周内给「N 天前」，更早给日期 */
const whenText = (r) => {
  const t = r.delivered_at || r.created_at
  if (!t) return ''
  const d = new Date(t)
  if (Number.isNaN(d.getTime())) return ''
  const diff = Date.now() - d.getTime()
  const day = 86400000
  const p = (n) => String(n).padStart(2, '0')
  if (diff < day && new Date().getDate() === d.getDate()) return `${p(d.getHours())}:${p(d.getMinutes())}`
  if (diff < 7 * day) return `${Math.floor(diff / day)} 天前`
  return `${d.getMonth() + 1}月${d.getDate()}日`
}

const openRun = (r) => {
  router.push({ path: '/planning/run', query: { run: r.id } })
}

onMounted(async () => {
  runs.value = await planningApi.listRuns()
})

const isPicked = (field, opt) => {
  const v = picked.value[field.key]
  return Array.isArray(v) ? v.includes(opt) : v === opt
}

const pick = (field, opt) => {
  if (field.type === 'multi') {
    const list = picked.value[field.key]
    const i = list.indexOf(opt)
    if (i >= 0) list.splice(i, 1)
    else list.push(opt)
  } else {
    picked.value[field.key] = opt
  }
}

const submitting = ref(false)
const submitError = ref('')

/**
 * 提交 → 建 run → 带 run_id 进工作台。
 *
 * 为什么要真建一次再跳：工作台是「任务实例」的视图，它需要一个 id 才能
 * 拉快照、订阅事件。原先只把参数塞进 query，工作台没有任务可显示。
 *
 * 不 await 图跑完 —— 后端 `POST /runs` 立即返回，图的推进由 SSE 带给工作台。
 */
const goWorkbench = async (params) => {
  if (submitting.value) return
  submitting.value = true
  submitError.value = ''
  try {
    const run = await planningApi.createRun({
      scene: params.scene || '',
      // 预算原话可能是「¥6万」，后端只存字符串不做换算；数字则直接给
      budget: String(params.budget ?? ''),
      duration: params.duration || '',
      constraints: params.constraints || (params.source === 'form' ? picked.value.constraints : []),
      // 采购主体：表单没收这个字段，先用场景兜底，后续可在表单里加
      subject: params.subject || ''
    })
    router.push({
      path: '/planning/run',
      query: {
        run: run.id,
        scene: params.scene || '',
        budget: String(params.budget || ''),
        duration: params.duration || ''
      }
    })
  } catch (e) {
    submitError.value = e?.message || '创建任务失败，请重试'
  } finally {
    submitting.value = false
  }
}

const startFromForm = () => {
  goWorkbench({
    scene: picked.value.scene,
    budget: picked.value.budget,
    duration: picked.value.when,
    constraints: picked.value.constraints,
    source: 'form'
  })
}

const startFromPreset = (preset) => {
  goWorkbench({
    ...preset.params,
    source: 'preset',
    preset: preset.id
  })
}
</script>

<style lang="less" scoped>
/* 布局交给全局 .page（page.less）。本文件只保留采购页特有的样式。
   刻意不再自绘 max-width / margin:auto —— 那会让内容左边界与全站其它页
   差出三百多像素（实测 405 vs 82）。
   印章已移入 PageHeader 的 #mark 插槽，本文件不再需要身份带样式。 */

/* 表单 */
.pe-form {
  border: 1px solid var(--border-strong);
  border-radius: var(--radius);
  background: var(--bg-surface);
  padding: 18px 20px 20px;
  max-width: 680px;
}
.pe-field {
  margin-bottom: 15px;
}
.pe-label {
  margin: 0 0 8px;
  font-size: 0.76rem;
  color: var(--text-muted);
  em {
    font-style: normal;
    color: var(--neg);
    margin-left: 3px;
  }
}
.pe-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.pe-chip {
  font-family: var(--font-body);
  font-size: 0.77rem;
  padding: 5px 13px;
  border-radius: 99px;
  border: 1px solid var(--border-strong);
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  transition: background-color 0.15s ease-out, border-color 0.15s ease-out, color 0.15s ease-out;
  &:hover { color: var(--text); }
  &.on {
    background: var(--accent-solid);
    border-color: var(--accent-solid);
    color: var(--on-accent);
  }
}
.pe-submit {
  width: 100%;
  margin-top: 4px;
  padding: 11px;
  font-family: var(--font-body);
  font-size: 0.84rem;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--accent-solid);
  color: var(--on-accent);
  cursor: pointer;
  transition: background-color 0.15s ease-out;
  &:hover:not(:disabled) { background: var(--accent-600); }
  &:disabled { opacity: 0.5; cursor: not-allowed; }
}
.pe-err {
  margin: 8px 0 0;
  font-size: 0.76rem;
  color: var(--neg);
}

/* ── 采购历史 ──
   一行一条，四段：状态 / 主体 / 规模 / 时间。
   状态在左且带色 —— 这一栏要回答的第一件事就是「哪些还要我管」。 */
.ph-list {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-surface);
  overflow: hidden;
}
.ph-row {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
  padding: 10px 14px;
  border: none;
  border-bottom: 1px solid var(--border);
  background: transparent;
  font-family: var(--font-body);
  text-align: left;
  cursor: pointer;
  transition: background-color 0.12s ease-out;
  &:last-child { border-bottom: none; }
  &:hover { background: var(--bg-sunken); }
}
/* 状态胶囊：颜色是这一栏的主要信息载体 */
.ph-state {
  flex: 0 0 auto;
  width: 52px;
  text-align: center;
  font-size: 0.66rem;
  padding: 2px 0;
  border-radius: 3px;
  background: var(--bg-sunken);
  color: var(--text-muted);
  &.is-delivered { color: var(--pos); }
  &.is-pending { color: var(--accent-700); background: var(--accent-50); }
  &.is-running { color: var(--info); }
  &.is-failed { color: var(--warn); }
}
.ph-main {
  flex: 1 1 auto;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.ph-title {
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-strong);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ph-sub {
  font-size: 0.7rem;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ph-num {
  flex: 0 0 auto;
  font-size: 0.7rem;
  color: var(--text-muted);
  white-space: nowrap;
}
.ph-when {
  flex: 0 0 auto;
  width: 62px;
  text-align: right;
  font-size: 0.68rem;
  color: var(--text-faint);
  white-space: nowrap;
}

/* 预设方案卡：容器用全局 .tile-grid / .tile，这里只调排版。
   .tile 已给白面板 + 圆角 + 细边框，不重复声明。 */
.pe-card {
  align-items: flex-start;
  gap: 4px;
  text-align: left;
  font-family: var(--font-body);
  cursor: pointer;
}
.pe-card-title {
  font-size: 0.84rem;
  font-weight: 600;
  color: var(--text-strong);
}
.pe-card-meta {
  font-size: 0.72rem;
  color: var(--text-muted);
}
.pe-card-desc {
  font-size: 0.72rem;
  line-height: 1.5;
  color: var(--text-faint);
}
</style>
