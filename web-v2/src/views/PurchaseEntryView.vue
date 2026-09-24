<template>
  <div class="page">
    <PageHeader
      title="采购规划"
      desc="装修、换季、搬家的组合采购 —— 我拆清单、排顺序、盯依赖"
    >
      <template #stats>
        <span class="stat-pill">进行中 <b>{{ runningCount }}</b> 个</span>
        <span v-if="awaitingCount" class="stat-pill">待你确认 <b>{{ awaitingCount }}</b> 个</span>
      </template>
      <template #actions>
        <a-button size="small" class="lucide-icon-btn" @click="router.push('/tasks')">
          <ClipboardList :size="14" /><span>任务状态</span>
        </a-button>
      </template>
    </PageHeader>

    <!-- 身份区：与欢迎页智能体最直接的区分 —— 用户一眼知道自己在跟谁说话。
         印章与 /proxy 的「礼」是同一种表达，全站一致；不再居中，
         改为左对齐的信息带，与其余页面同一阅读起点。 -->
    <section class="pe-id">
      <span class="pe-sig">采</span>
      <div class="pe-id-text">
        <p class="pe-name">采办 · 采购规划顾问</p>
        <p class="pe-desc">把模糊需求收敛成结构化参数，交给工作台执行</p>
      </div>
    </section>

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
   差出三百多像素（实测 405 vs 82）。 */

/* 身份带：左对齐，与页头同一阅读起点 */
.pe-id {
  display: flex;
  align-items: center;
  gap: 11px;
  margin-bottom: 22px;
}
.pe-id-text { min-width: 0; }
.pe-sig {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 9px;
  background: var(--accent-50);
  color: var(--accent-700);
  font-size: 0.92rem;
  font-weight: 600;
}
.pe-name {
  margin: 0;
  font-family: var(--font-display);
  font-size: 0.98rem;
  font-weight: 600;
  color: var(--text-strong);
}
.pe-desc {
  margin: 2px 0 0;
  font-size: 0.8rem;
  line-height: 1.6;
  color: var(--text-muted);
}

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
