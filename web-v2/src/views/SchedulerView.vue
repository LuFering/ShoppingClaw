<template>
  <div class="page">
    <PageHeader
      title="定时任务"
      desc="按计划执行监控与 AI 汇总，命中结果写入运行日志（数据对接 /api/tasks）"
    >
      <template #stats>
        <span class="stat-pill">启用 <b>{{ enabledCount }}</b></span>
        <span class="stat-pill">共 <b>{{ moduleTasks.length }}</b> 个</span>
        <span class="stat-pill">累计执行 <b>{{ totalRuns }}</b> 次</span>
      </template>
      <template #actions>
        <a-button type="primary" class="lucide-icon-btn" :loading="loading" @click="startCreate">
          <Plus :size="14" /><span>新增任务</span>
        </a-button>
      </template>
    </PageHeader>

    <!-- 模块切换 -->
    <nav class="module-tabs">
      <button class="module-tab" :class="{ on: view === 'regular' }" @click="switchModule('regular')">
        普通任务 <span v-if="allTasks.length" class="tab-num num">{{ allTasks.filter(t => !t.isAi).length }}</span>
      </button>
      <button class="module-tab" :class="{ on: view === 'ai' }" @click="switchModule('ai')">
        AI 自动化 <span v-if="allTasks.length" class="tab-num num">{{ allTasks.filter(t => t.isAi).length }}</span>
      </button>
      <span class="ai-note">后端执行器：价格 / 库存 / 优惠券 / 榜单 / 店铺 / Agent</span>
    </nav>

    <!-- 工具栏 -->
    <div class="page-toolbar">
      <input v-model="keyword" class="page-search" type="search" placeholder="搜索任务名或对象…" />
      <a-select v-model:value="typeFilter" size="small" class="type-select" :options="typeOptions" />
      <a-checkbox v-model:checked="onlyEnabled">只看已启用</a-checkbox>
      <a-button size="small" class="logs-trigger" :loading="logsLoading" @click="openLogs">
        运行日志<span v-if="allLogs.length" class="num logs-count">{{ allLogs.length }}</span>
      </a-button>
    </div>

    <div v-if="loading" class="page-empty">
      <a-spin tip="加载任务中…" />
    </div>

    <a-empty
      v-else-if="!visibleTasks.length"
      class="page-empty"
      :image="Empty.PRESENTED_IMAGE_SIMPLE"
      :description="tasksError || (allTasks.length ? '没有匹配的任务' : '还没有任务，从「新增任务」的模板开始')"
    >
      <a-button v-if="!tasksError" type="primary" @click="startCreate">新增任务</a-button>
      <a-button v-else @click="loadAll">重试</a-button>
    </a-empty>

    <!-- 任务表 -->
    <table v-else class="tbl">
      <thead>
        <tr>
          <th class="w-on">启用</th>
          <th class="w-name">任务</th>
          <th class="w-target">监控对象 / 指令</th>
          <th class="w-freq">频率</th>
          <th class="w-next">下次执行</th>
          <th class="w-last">上次执行</th>
          <th class="w-act">操作</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="t in visibleTasks" :key="t.id" :class="{ off: !t.enabled }">
          <td>
            <a-switch :checked="t.enabled" size="small" @change="(v) => toggleEnabled(t, v)" />
          </td>
          <td>
            <span class="task-name">{{ t.name }}</span>
            <span class="task-meta">{{ typeLabel(t.type) }}<template v-if="t.isAi"> · AI</template></span>
          </td>
          <td>
            <p class="cell-text" :title="t.target">{{ t.target }}</p>
            <p v-if="t.lastSummary" class="cell-sub">{{ t.lastSummary }}</p>
          </td>
          <td><span class="cell-text">{{ t.freq }}</span></td>
          <td class="mono muted">{{ t.nextAt }}</td>
          <td>
            <span class="state" :class="'rs-' + (t.busy ? 'run' : t.lastResult)">
              <span class="dot" />{{ t.busy ? '执行中' : resultLabel(t.lastResult) }}
            </span>
            <span class="sub mono">{{ t.lastAt }}</span>
          </td>
          <td>
            <div class="row-actions">
              <button class="icon-btn" :disabled="t.busy" title="立即执行" @click="runNow(t)">
                <RefreshCw :size="14" :class="{ spin: t.busy }" />
              </button>
              <button class="icon-btn" title="编辑" @click="openEdit(t)"><Pencil :size="14" /></button>
              <button class="icon-btn is-danger" title="删除" @click="removeTask(t)"><Trash2 :size="14" /></button>
            </div>
          </td>
        </tr>
      </tbody>
    </table>

    <!-- 运行日志弹窗 -->
    <a-modal v-model:open="logsOpen" title="运行日志" :width="760" :footer="null">
      <div class="modal-logs">
        <a-empty
          v-if="!logsLoading && !allLogs.length"
          class="logs-empty"
          :image="Empty.PRESENTED_IMAGE_SIMPLE"
          :description="logsError || '暂无运行记录（任务执行后写入）'"
        />
        <a-spin v-else-if="logsLoading" class="logs-spin" />
        <table v-else class="tbl log-tbl">
          <thead>
            <tr>
              <th class="w-lg-time">时间</th>
              <th class="w-lg-task">任务</th>
              <th class="w-lg-result">结果</th>
              <th class="w-lg-msg">说明</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="lg in allLogs" :key="lg.id">
              <td class="mono muted">{{ lg.time }}</td>
              <td>{{ lg.taskName }}</td>
              <td>
                <span class="state" :class="'rs-' + lg.result"><span class="dot" />{{ resultLabel(lg.result) }}</span>
              </td>
              <td><p class="log-msg">{{ lg.msg || '—' }}</p></td>
            </tr>
          </tbody>
        </table>
      </div>
    </a-modal>

    <!-- 新增 / 编辑：模板(类型) → 结构化表单 -->
    <a-modal
      v-model:open="formOpen"
      :title="step === 'template' ? '选择任务类型' : (editingId ? '编辑任务' : '新增任务')"
      :width="560"
      :confirm-loading="saving"
      @ok="step === 'template' ? null : saveForm()"
    >
      <div class="modal-body">
        <template v-if="step === 'template'">
          <p class="step-hint">选择一个类型创建任务，参数可按执行器要求填写</p>
          <div class="tpl-list">
            <button
              v-for="td in templateDefs"
              :key="td.type"
              class="tpl-row"
              @click="useType(td.type)"
            >
              <span class="tpl-name">{{ td.label }}</span>
              <span class="tpl-desc">{{ td.desc }}</span>
              <span class="tpl-preset mono">{{ td.presetNote }}</span>
            </button>
          </div>
        </template>

        <template v-else>
          <div class="form-item">
            <label>任务名称</label>
            <a-input v-model:value="form.name" placeholder="如：添可芙万盯价" />
          </div>

          <!-- 按类型动态参数 -->
          <div v-for="p in currentParams" :key="p.key" class="form-item">
            <label>{{ p.label }}<span v-if="!p.optional" class="req">*</span></label>
            <a-input
              v-if="p.type !== 'textarea'"
              v-model:value="form.params[p.key]"
              :class="{ mono: p.type === 'money' }"
              :placeholder="p.placeholder"
            />
            <a-textarea v-else v-model:value="form.params[p.key]" :rows="3" :placeholder="p.placeholder" />
            <p v-if="p.type === 'money'" class="field-hint">单位：元（提交时自动转为分）</p>
          </div>

          <div class="form-item">
            <label>触发频率</label>
            <a-segmented v-model:value="form.freqMode" size="small" :options="freqModes" />
            <div v-if="form.freqMode === 'interval'" class="sub-input">
              <span>间隔</span>
              <a-select
                v-model:value="form.intervalHours"
                size="small"
                class="sub-select"
                :options="[1, 2, 3, 4, 6, 8, 12, 24].map((h) => ({ label: `${h} 小时`, value: h }))"
              />
            </div>
            <div v-if="form.freqMode === 'daily'" class="sub-input">
              <span>每天</span>
              <input v-model="form.dailyTime" type="time" class="input sel" />
            </div>
            <div v-if="form.freqMode === 'weekly'" class="sub-input">
              <span>每周</span>
              <span class="wd-row">
                <button v-for="d in weekdays" :key="d.v" class="wd" :class="{ on: form.weekDays.includes(d.v) }" @click="toggleDay(d.v)">{{ d.t }}</button>
              </span>
              <input v-model="form.dailyTime" type="time" class="input sel" />
            </div>
          </div>

          <div class="form-item">
            <label>通知方式</label>
            <div class="checks">
              <a-checkbox v-model:checked="form.notify.inapp">站内</a-checkbox>
              <a-checkbox v-model:checked="form.notify.email">邮件</a-checkbox>
            </div>
          </div>
        </template>
      </div>

      <template #footer>
        <template v-if="step === 'template'">
          <a-button @click="formOpen = false">取消</a-button>
        </template>
        <template v-else>
          <a-button @click="step = 'template'">← 上一步</a-button>
          <a-button type="primary" :loading="saving" @click="saveForm">{{ editingId ? '保存更改' : '创建任务' }}</a-button>
        </template>
      </template>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import { Modal, message, Empty } from 'ant-design-vue'
import { Plus, RefreshCw, Pencil, Trash2 } from 'lucide-vue-next'
import PageHeader from '@/components/PageHeader.vue'
import { taskApi, PLATFORMS } from '@/apis/task_api'

const resultLabel = (r) => ({ ok: '成功', fail: '失败', hit: '命中', empty: '无变化', run: '执行中' }[r] || r)

const typeMeta = {
  price: { label: '降价' }, coupon: { label: '优惠券' }, stock: { label: '库存' },
  rank: { label: '榜单' }, shop: { label: '店铺' }, agent: { label: 'AI' }
}
const typeLabel = (t) => (typeMeta[t]?.label || t) + '监控'

// ===== 模板（类型）定义：参数对齐后端各 executor 的 task_params =====
const templateDefs = [
  { type: 'price', label: '降价提醒', desc: '商品价格降至目标价时命中提醒', presetNote: '默认每 2 小时',
    params: [
      { key: 'product_name', label: '商品名称', placeholder: '如：添可芙万 3.0' },
      { key: 'target_price', label: '目标价（元）', type: 'money', placeholder: '如 1999', optional: true }
    ] },
  { type: 'stock', label: '补货提醒', desc: '目标商品缺货恢复时提醒', presetNote: '默认每 6 小时',
    params: [
      { key: 'product_name', label: '商品名称', placeholder: '如：Incase Icon 灰色 M' }
    ] },
  { type: 'coupon', label: '优惠券监控', desc: '出现可用券（可选最低面额）时提醒', presetNote: '默认每天 09:00',
    params: [
      { key: 'keyword', label: '搜索关键词', placeholder: '如：戴森 V12' },
      { key: 'min_coupon_amount', label: '最低券面额（元）', type: 'money', placeholder: '如 100', optional: true }
    ] },
  { type: 'rank', label: '榜单监测', desc: '品类热榜 Top 变化 / 目标商品排名', presetNote: '默认每周一 08:00',
    params: [
      { key: 'keyword', label: '榜单关键词', placeholder: '如：扫地机器人' },
      { key: 'product_name', label: '跟踪商品（可选）', placeholder: '盯排名的商品', optional: true }
    ] },
  { type: 'shop', label: '店铺活动', desc: '店铺上新、满减开始时提醒', presetNote: '默认每 3 小时',
    params: [
      { key: 'shop_name', label: '店铺名称', placeholder: '如：添可官方旗舰店' }
    ] },
  { type: 'agent', label: 'AI 自动化', desc: '按指令执行一次 Agent 对话并汇总', presetNote: '默认每天 21:00',
    params: [
      { key: 'prompt', label: '执行指令', type: 'textarea', placeholder: '如：汇总今日对话，生成待确认草稿' }
    ] }
]

// ===== 数据（真实 /api/tasks）=====
const allTasks = ref([])
const allLogs = ref([])
const loading = ref(false)
const tasksError = ref('')
const logsLoading = ref(false)
const logsError = ref('')

const loadAll = async () => {
  loading.value = true
  tasksError.value = ''
  try {
    const list = await taskApi.getTasks()
    // 兼容后端旧数据：无 status 的视为 active
    allTasks.value = list
  } catch (e) {
    console.error('任务加载失败:', e)
    tasksError.value = '任务接口不可用（后端未启动？）'
    allTasks.value = []
  } finally {
    loading.value = false
  }
}

// ===== 列表过滤 =====
const view = ref('regular')
const keyword = ref('')
const typeFilter = ref('all')
const onlyEnabled = ref(false)

const moduleTasks = computed(() => {
  const ai = view.value === 'ai'
  return allTasks.value.filter((t) => t.isAi === ai)
})
const typeOptions = computed(() => {
  const base = view.value === 'ai'
    ? [{ value: 'agent', label: 'AI' }]
    : Object.keys(typeMeta).filter((k) => k !== 'agent').map((k) => ({ value: k, label: typeMeta[k].label }))
  return [{ value: 'all', label: '全部类型' }, ...base]
})
const enabledCount = computed(() => moduleTasks.value.filter((t) => t.enabled).length)
const totalRuns = computed(() => allTasks.value.reduce((s, t) => s + (t.runCount || 0), 0))
const visibleTasks = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  return moduleTasks.value.filter((t) => {
    if (typeFilter.value !== 'all' && t.type !== typeFilter.value) return false
    if (onlyEnabled.value && !t.enabled) return false
    if (kw && !`${t.name} ${t.target}`.toLowerCase().includes(kw)) return false
    return true
  })
})
const switchModule = (m) => { view.value = m; keyword.value = ''; typeFilter.value = 'all' }

// ===== 行操作 =====
const toggleEnabled = async (t, v) => {
  const prev = t.enabled
  t.enabled = v
  try {
    await taskApi.setEnabled(t.id, v)
  } catch (e) {
    t.enabled = prev
    message.error('启停失败：' + (e.message || e))
  }
}

const runNow = async (t) => {
  if (t.busy) return
  t.busy = true
  try {
    await taskApi.triggerTask(t.id)
    message.success(`已触发「${t.name}」，结果稍后写入运行日志`)
  } catch (e) {
    message.error('触发失败：' + (e.message || e))
  } finally {
    setTimeout(() => { t.busy = false }, 600)
  }
}

const removeTask = (t) => {
  Modal.confirm({
    title: `删除任务「${t.name}」？`,
    content: '删除后不再按计划执行，历史日志保留。',
    okText: '删除',
    okType: 'danger',
    cancelText: '取消',
    async onOk() {
      await taskApi.deleteTask(t.id)
      allTasks.value = allTasks.value.filter((x) => x.id !== t.id)
      message.success('已删除')
    }
  })
}

// ===== 日志（弹窗打开时拉当前模块各任务最近日志并合并）=====
const logsOpen = ref(false)
const openLogs = async () => {
  logsOpen.value = true
  logsLoading.value = true
  logsError.value = ''
  try {
    const targets = moduleTasks.value.slice(0, 8)
    const results = await Promise.all(targets.map((t) => taskApi.getTaskLogs(t.id, 3).catch(() => [])))
    const nameById = Object.fromEntries(targets.map((t) => [t.id, t.name]))
    const merged = results.flat().sort((a, b) => b.time.localeCompare(a.time)).slice(0, 60)
    allLogs.value = merged.map((l) => ({ ...l, taskName: nameById[l.taskId] || '' }))
  } catch {
    logsError.value = '日志加载失败'
    allLogs.value = []
  } finally {
    logsLoading.value = false
  }
}

// ===== 表单（模板 → 结构化参数）=====
const formOpen = ref(false)
const saving = ref(false)
const editingId = ref(null)
const step = ref('template')
const freqModes = [
  { value: 'interval', label: '固定间隔' },
  { value: 'daily', label: '每天固定' },
  { value: 'weekly', label: '每周固定' }
]
const weekdays = [
  { v: 1, t: '一' }, { v: 2, t: '二' }, { v: 3, t: '三' }, { v: 4, t: '四' }, { v: 5, t: '五' }, { v: 6, t: '六' }, { v: 0, t: '日' }
]

const form = ref(blankForm())
const currentParams = computed(() => {
  const def = templateDefs.find((d) => d.type === form.value.type)
  return def ? def.params : []
})

function blankForm() {
  return {
    type: 'price', name: '', params: {},
    freqMode: 'interval', intervalHours: 2, dailyTime: '21:00', weekDays: [1, 2, 3, 4, 5],
    notify: { inapp: true, email: false }
  }
}

const startCreate = () => {
  editingId.value = null
  step.value = 'template'
  formOpen.value = true
}

const useType = (type) => {
  const def = templateDefs.find((d) => d.type === type)
  form.value = blankForm()
  form.value.type = type
  form.value.name = def.label
  step.value = 'form'
}

const openEdit = (t) => {
  editingId.value = t.id
  step.value = 'form'
  const f = blankForm()
  f.type = t.type
  f.name = t.name
  // 后端参数回填：金额（分→元）
  const p = t.taskParams || {}
  f.params = { ...p }
  for (const k of ['target_price', 'min_coupon_amount']) {
    if (f.params[k] != null) f.params[k] = (f.params[k] / 100).toFixed(0)
  }
  if (t.intervalSeconds) {
    f.freqMode = 'interval'
    f.intervalHours = t.intervalSeconds / 3600
  } else {
    // cron → daily/weekly（本项目生成格式）
    const parts = String(t.cronExpression || '').trim().split(/\s+/)
    if (parts.length === 5) {
      const [, min, hour, , dow] = parts
      f.dailyTime = `${hour}:${min}`
      if (dow !== '*') {
        f.freqMode = 'weekly'
        f.weekDays = String(dow).split(',').map(Number)
      } else f.freqMode = 'daily'
    }
  }
  form.value = f
}

const toggleDay = (v) => {
  const set = new Set(form.value.weekDays)
  if (set.has(v)) set.delete(v); else set.add(v)
  form.value.weekDays = [...set]
}

// 金额参数 → 分
const moneyToCents = (v) => {
  const n = Number(String(v).replace(/[^\d.]/g, ''))
  return Number.isFinite(n) && n > 0 ? Math.round(n * 100) : undefined
}

const saveForm = async () => {
  const f = form.value
  if (!f.name.trim()) { message.warning('请填写任务名称'); return }
  // 校验必填参数 + 金额转分
  const taskParams = {}
  for (const p of currentParams.value) {
    const raw = (f.params[p.key] ?? '').toString().trim()
    if (!raw) {
      if (!p.optional) { message.warning(`请填写「${p.label}」`); return }
      continue
    }
    taskParams[p.key] = p.type === 'money' ? moneyToCents(raw) : raw
  }
  // 平台：执行器均对接 taobao_mcp（agent 类型除外，只收 prompt）
  if (f.type !== 'agent' && PLATFORMS[0]) taskParams.platform = PLATFORMS[0].value

  saving.value = true
  try {
    const payload = {
      name: f.name.trim(),
      type: f.type,
      taskParams,
      freqMode: f.freqMode,
      intervalHours: f.intervalHours,
      dailyTime: f.dailyTime,
      weekDays: f.weekDays,
      notifyEnabled: f.notify.inapp || f.notify.email
    }
    if (editingId.value) {
      await taskApi.updateTask(editingId.value, payload)
      message.success('已保存')
    } else {
      await taskApi.createTask(payload)
      message.success('任务已创建')
    }
    formOpen.value = false
    loadAll()
  } catch (e) {
    message.error('保存失败：' + (e.message || e))
  } finally {
    saving.value = false
  }
}

watch(() => view.value, () => { if (logsOpen.value) openLogs() })

// 初始加载（组件挂载即拉取；keepAlive 下仅首次）
loadAll()
</script>

<style lang="less" scoped>
.module-tabs {
  display: flex;
  align-items: center;
  gap: 18px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--border);
  margin-bottom: 4px;
}
.module-tab {
  border: none;
  background: transparent;
  padding: 0 0 3px;
  font-size: 0.95rem;
  font-family: var(--font-body);
  color: var(--text-muted);
  cursor: pointer;
  border-bottom: 2px solid transparent;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  transition: color 0.15s ease-out, border-color 0.15s ease-out;
  &:hover { color: var(--text-strong); }
  &.on { color: var(--text-strong); font-weight: 600; border-bottom-color: var(--accent-500); }
}
.tab-num { font-size: 0.72rem; color: var(--text-faint); }
.ai-note { margin-left: auto; font-size: 0.78rem; color: var(--text-muted); }

.type-select { min-width: 104px; }

/* 任务表 */
.tbl { width: 100%; border-collapse: collapse; table-layout: fixed; }
.tbl thead th {
  text-align: left;
  font-size: 0.72rem;
  font-weight: 500;
  letter-spacing: 0.05em;
  color: var(--text-faint);
  padding: 6px 10px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.tbl tbody td { padding: 10px; border-bottom: 1px solid var(--border); vertical-align: top; }
.tbl tbody tr { transition: background 0.15s ease-out; }
.tbl tbody tr:hover td { background: var(--bg-surface); }
.tbl tbody tr:last-child td { border-bottom: none; }
tr.off td { opacity: 0.55; }

.w-on { width: 5%; } .w-name { width: 15%; } .w-target { width: 24%; } .w-freq { width: 12%; } .w-next { width: 12%; } .w-last { width: 14%; } .w-act { width: 8%; }
.w-lg-time { width: 12%; } .w-lg-task { width: 19%; } .w-lg-result { width: 11%; }

.task-name { font-weight: 600; color: var(--text-strong); display: block; }
.task-meta { font-size: 0.72rem; color: var(--text-muted); display: block; margin-top: 1px; }
.cell-text { margin: 0; color: var(--text); font-size: 0.85rem; line-height: 1.5; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.cell-sub { margin: 1px 0 0; font-size: 0.72rem; color: var(--text-faint); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.mono, .num { font-family: var(--font-mono); font-variant-numeric: tabular-nums; }
.muted { color: var(--text-muted); }
.sub { display: block; font-size: 0.7rem; color: var(--text-faint); margin-top: 2px; }
.log-msg { margin: 0; color: var(--text-muted); font-size: 0.82rem; line-height: 1.5; }

.state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 0.8rem;
  font-weight: 500;
  white-space: nowrap;
  .dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex-shrink: 0; }
}
.rs-ok { color: var(--pos); }
.rs-hit { color: var(--accent-700); }
.rs-empty { color: var(--text-faint); font-weight: 400; }
.rs-fail { color: var(--neg); }
.rs-run { color: var(--info); }

.icon-btn { display: inline-flex; align-items: center; justify-content: center; width: 26px; height: 26px; border: none; border-radius: var(--radius-sm); background: transparent; color: var(--text-muted); cursor: pointer; transition: color 0.15s ease-out, background 0.15s ease-out; &:hover { color: var(--accent-600); background: var(--accent-50); } &:disabled { opacity: 0.4; cursor: not-allowed; } &.is-danger:hover { color: var(--neg); background: var(--bg-sunken); } }
@keyframes rot { to { transform: rotate(360deg); } }
.spin { animation: rot 0.8s linear infinite; }

.logs-trigger { margin-left: auto; }
.logs-trigger .logs-count { margin-left: 6px; font-size: 0.72rem; color: var(--text-faint); }
.modal-logs { max-height: 56vh; overflow-y: auto; }
.logs-spin { display: block; padding: 40px 0; text-align: center; }
.logs-empty { padding: 18px 0; }
.log-tbl { margin-top: 2px; }

/* 弹窗表单 */
.modal-body { max-height: min(60vh, 560px); overflow-y: auto; }
.step-hint { font-size: 0.8rem; color: var(--text-muted); margin: 0 0 10px; }
.tpl-list { display: flex; flex-direction: column; gap: 6px; }
.tpl-row { display: flex; align-items: baseline; gap: 10px; width: 100%; text-align: left; padding: 9px 12px; background: var(--bg-sunken); border: 1px solid var(--border); border-radius: var(--radius-sm); cursor: pointer; font-family: var(--font-body); transition: border-color 0.15s ease-out; &:hover { border-color: var(--accent-500); } }
.tpl-name { font-weight: 600; color: var(--text-strong); font-size: 0.88rem; flex-shrink: 0; min-width: 84px; }
.tpl-desc { flex: 1; font-size: 0.8rem; color: var(--text-muted); }
.tpl-preset { font-size: 0.7rem; color: var(--text-faint); }

.form-item { margin-bottom: 14px; > label { display: block; font-size: 0.8rem; color: var(--text-muted); margin-bottom: 6px; .req { color: var(--neg); margin-left: 2px; } } }
.field-hint { margin: 4px 0 0; font-size: 0.72rem; color: var(--text-faint); }
.input.sel { width: auto; height: 28px; padding: 0 8px; font-family: var(--font-body); font-size: 0.82rem; color: var(--text); background: var(--bg-surface); border: 1px solid var(--border-strong); border-radius: var(--radius-sm); outline: none; &:focus { border-color: var(--accent-500); } }
.sub-input { display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 0.8rem; color: var(--text-muted); flex-wrap: wrap; }
.wd-row { display: inline-flex; gap: 4px; }
.wd { width: 24px; height: 24px; border-radius: 5px; border: 1px solid var(--border-strong); background: var(--bg-surface); font-size: 0.78rem; color: var(--text-muted); cursor: pointer; transition: border-color 0.15s ease-out, color 0.15s ease-out; &:hover { border-color: var(--accent-400); } &.on { border-color: var(--accent-500); color: var(--accent-700); font-weight: 600; } }
.checks { display: flex; gap: 16px; font-size: 0.84rem; }
.page-empty { padding: 40px 0; text-align: center; }
</style>
